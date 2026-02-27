"""
Background profiler — extracts preference signals from each chat turn
and updates the user profile. Never touches allergy data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.gemma import GemmaError, call_gemma_json
from app.utils.prompts import build_profiler_prompt

logger = logging.getLogger(__name__)

# Fields the profiler is allowed to update — allergies deliberately excluded
_ALLOWED_PREFERENCE_KEYS = {
    "dietary", "vibes", "cuisine_affinity", "cuisine_aversion", "price_comfort",
}


async def update_user_profile(
    uid: UUID,
    message: str,
    agent_response: dict[str, Any],
    db: AsyncSession,
) -> None:
    """
    Fire-and-forget profiler: extract NEW preference signals from the conversation
    turn and update the user's preferences, dietary_flags, vibe_tags,
    interaction_count, and last_active_at.

    NEVER extracts or modifies allergy data.
    Allergies are only updated via PATCH /users/{uid}/allergies (Backend-controlled,
    based on explicit user action — never inferred from chat).

    Entirely wrapped in try/except — never raises.
    """
    try:
        response_summary = agent_response.get("message", "")
        prompt = build_profiler_prompt(message, response_summary)

        extracted: dict[str, Any] = await call_gemma_json(prompt)

        # Sanitise — strip any allergy-related keys that should not appear
        extracted = {
            k: v for k, v in extracted.items() if k in _ALLOWED_PREFERENCE_KEYS
        }

        if not extracted:
            # Nothing new to update — still bump interaction count
            await _bump_interaction(uid, db)
            return

        # Fetch current preferences
        result = await db.execute(
            text(
                "SELECT preferences, dietary_flags, vibe_tags "
                "FROM users WHERE uid = :uid"
            ),
            {"uid": str(uid)},
        )
        row = result.fetchone()
        if not row:
            logger.warning("Profiler: user %s not found, skipping update.", uid)
            return

        current_prefs = dict(row.preferences or {})

        # Deep merge — lists are unioned, scalar values are replaced
        for key, value in extracted.items():
            if isinstance(value, list):
                existing = current_prefs.get(key, [])
                merged = list(dict.fromkeys(existing + value))  # deduplicate
                current_prefs[key] = merged
            else:
                current_prefs[key] = value

        # Rebuild denormalised arrays
        dietary_flags = current_prefs.get("dietary", [])
        vibe_tags = current_prefs.get("vibes", [])

        await db.execute(
            text("""
                UPDATE users
                SET preferences       = :preferences,
                    dietary_flags     = :dietary_flags,
                    vibe_tags         = :vibe_tags,
                    interaction_count = interaction_count + 1,
                    last_active_at    = :now,
                    updated_at        = :now
                WHERE uid = :uid
            """),
            {
                "preferences": json.dumps(current_prefs),  # JSONB needs serialized text
                "dietary_flags": dietary_flags,
                "vibe_tags": vibe_tags,
                "now": datetime.now(timezone.utc),
                "uid": str(uid),
            },
        )
        await db.commit()
        logger.debug("Profiler updated user %s with keys: %s", uid, list(extracted.keys()))

        # Pre-warm recommendation cache after a successful profile update
        from app.services.recommendation_service import prewarm_recommendations  # noqa: PLC0415
        asyncio.create_task(prewarm_recommendations(uid))

    except Exception as exc:
        logger.error("Profiler failed for user %s: %s", uid, exc)
        # Never propagate — profiler failure must not affect the chat response


async def _bump_interaction(uid: UUID, db: AsyncSession) -> None:
    """Increment interaction_count and last_active_at even when no new signals found."""
    try:
        await db.execute(
            text("""
                UPDATE users
                SET interaction_count = interaction_count + 1,
                    last_active_at    = :now,
                    updated_at        = :now
                WHERE uid = :uid
            """),
            {"now": datetime.now(timezone.utc), "uid": str(uid)},
        )
        await db.commit()
    except Exception as exc:
        logger.error("Failed to bump interaction count for user %s: %s", uid, exc)
