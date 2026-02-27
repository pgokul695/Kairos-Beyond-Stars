"""
User management endpoints — all protected by X-Service-Token header.
Called by the Backend after authentication events.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.user import (
    AllergiesPatch,
    AllergyFlagsResponse,
    InteractionListResponse,
    InteractionSummary,
    UserCreate,
    UserPreferencesPatch,
    UserRead,
)
from app.utils.allergy_data import ALLERGEN_SYNONYMS, CANONICAL_ALLERGENS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


# ── Auth dependency ──────────────────────────────────────────────────────────


async def verify_service_token(
    x_service_token: str = Header(..., alias="X-Service-Token"),
) -> None:
    """Verify that the inter-service token matches the configured secret."""
    if x_service_token != settings.service_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalise_allergen(a: str) -> str:
    """Map a synonym to its canonical allergen name, or return as-is if already canonical."""
    a_lower = a.lower().strip()
    return ALLERGEN_SYNONYMS.get(a_lower, a_lower)


def _build_allergy_flags(allergies: dict) -> list[str]:
    """Build a flat, deduplicated list of canonical allergen names from an allergies dict."""
    confirmed = allergies.get("confirmed", [])
    intolerances = allergies.get("intolerances", [])
    all_raw = confirmed + intolerances
    normalised = [_normalise_allergen(a) for a in all_raw]
    return list(dict.fromkeys(normalised))  # deduplicate preserving order


def _deep_merge(base: dict, update: dict) -> dict:
    """Deep-merge update into base. Lists are unioned; scalars are replaced."""
    result = dict(base)
    for key, value in update.items():
        if isinstance(value, list) and isinstance(result.get(key), list):
            result[key] = list(dict.fromkeys(result[key] + value))
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/{uid}", status_code=status.HTTP_201_CREATED)
async def create_or_get_user(
    uid: UUID,
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> dict:
    """
    Create a new user profile or return an existing one (idempotent).
    Returns {"uid": "...", "created": true} on first call,
            {"uid": "...", "created": false} on subsequent calls.
    """
    result = await db.execute(
        text("SELECT uid FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    existing = result.fetchone()

    if existing:
        return {"uid": str(uid), "created": False}

    allergy_flags = body.allergy_flags or _build_allergy_flags(body.allergies)

    try:
        await db.execute(
            text("""
                INSERT INTO users
                    (uid, preferences, allergies, allergy_flags,
                     dietary_flags, vibe_tags, preferred_price_tiers)
                VALUES
                    (:uid, :preferences, :allergies, :allergy_flags,
                     :dietary_flags, :vibe_tags, :price_tiers)
            """),
            {
                "uid": str(uid),
                "preferences": json.dumps(body.preferences),
                "allergies": json.dumps(body.allergies),
                "allergy_flags": allergy_flags,
                "dietary_flags": body.dietary_flags,
                "vibe_tags": body.vibe_tags,
                "price_tiers": body.preferred_price_tiers,
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to create user %s: %s", uid, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        ) from exc

    return {"uid": str(uid), "created": True}


@router.get("/{uid}", response_model=UserRead)
async def get_user(
    uid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> UserRead:
    """Return the full user profile."""
    result = await db.execute(
        text("""
            SELECT uid, preferences, allergies, allergy_flags, dietary_flags,
                   vibe_tags, preferred_price_tiers, interaction_count,
                   last_active_at, created_at, updated_at
            FROM users WHERE uid = :uid
        """),
        {"uid": str(uid)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )
    return UserRead.model_validate(dict(row._mapping))


@router.patch("/{uid}")
async def patch_user_preferences(
    uid: UUID,
    body: UserPreferencesPatch,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> dict:
    """
    Deep-merge body.preferences into the existing preferences JSONB.
    Does NOT touch allergies.
    """
    result = await db.execute(
        text("SELECT preferences FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )

    merged = _deep_merge(row.preferences or {}, body.preferences)

    try:
        await db.execute(
            text("""
                UPDATE users
                SET preferences = :preferences, updated_at = :now
                WHERE uid = :uid
            """),
            {"preferences": json.dumps(merged), "now": datetime.now(timezone.utc), "uid": str(uid)},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update preferences",
        ) from exc

    return {"uid": str(uid), "updated": True}


@router.patch("/{uid}/allergies", response_model=AllergyFlagsResponse)
async def patch_user_allergies(
    uid: UUID,
    body: AllergiesPatch,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> AllergyFlagsResponse:
    """
    FULL REPLACE of the user's allergies object.
    Agent rebuilds allergy_flags[] from the new allergies object.
    This is the ONLY way allergy data is updated — never inferred from chat.
    """
    result = await db.execute(
        text("SELECT uid FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )

    new_allergies = {
        "confirmed": body.confirmed,
        "intolerances": body.intolerances,
        "severity": body.severity,
    }
    allergy_flags = _build_allergy_flags(new_allergies)

    try:
        await db.execute(
            text("""
                UPDATE users
                SET allergies     = :allergies,
                    allergy_flags = :allergy_flags,
                    updated_at    = :now
                WHERE uid = :uid
            """),
            {
                "allergies": json.dumps(new_allergies),
                "allergy_flags": allergy_flags,
                "now": datetime.now(timezone.utc),
                "uid": str(uid),
            },
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update allergies",
        ) from exc

    return AllergyFlagsResponse(uid=uid, allergy_flags=allergy_flags, updated=True)


@router.delete("/{uid}")
async def delete_user(
    uid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> Response:
    """Delete a user and cascade-delete all their interactions."""
    result = await db.execute(
        text("SELECT uid FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )

    try:
        await db.execute(
            text("DELETE FROM users WHERE uid = :uid"),
            {"uid": str(uid)},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{uid}/interactions", response_model=InteractionListResponse)
async def list_interactions(
    uid: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_response: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> InteractionListResponse:
    """Paginated list of interactions for a user."""
    result = await db.execute(
        text("SELECT uid FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )

    count_result = await db.execute(
        text("SELECT COUNT(*) FROM interactions WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    total = count_result.scalar() or 0

    response_col = "agent_response" if include_response else "'{}' AS agent_response"
    rows_result = await db.execute(
        text(f"""
            SELECT id, uid, user_query, {response_col}, ui_type,
                   restaurant_ids, allergy_warnings_shown, allergens_flagged,
                   prompt_tokens, completion_tokens, created_at
            FROM interactions
            WHERE uid = :uid
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"uid": str(uid), "limit": limit, "offset": offset},
    )
    rows = rows_result.fetchall()

    interactions = [
        InteractionSummary.model_validate(dict(r._mapping)) for r in rows
    ]
    return InteractionListResponse(
        interactions=interactions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{uid}/interactions")
async def clear_interactions(
    uid: UUID,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_service_token),
) -> Response:
    """Clear all interaction history for a user (keeps the user record)."""
    result = await db.execute(
        text("SELECT uid FROM users WHERE uid = :uid"),
        {"uid": str(uid)},
    )
    if not result.fetchone():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"X-Error-Code": "USER_NOT_FOUND"},
        )

    try:
        await db.execute(
            text("DELETE FROM interactions WHERE uid = :uid"),
            {"uid": str(uid)},
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear interactions",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
