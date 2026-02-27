"""
Orchestrator — the 5-step AI reasoning loop that powers every chat turn.
Steps: context retrieval → query decomposition → hybrid search →
       evaluation → allergy guard → response construction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.schemas.chat import ChatMessage
from app.schemas.restaurant import GenerativeUIPayload, RadarScores, RestaurantResult
from app.services.allergy_guard import AllergyCheckResult, AllergyGuard
from app.services.gemma import GemmaError, call_gemma_json
from app.services.hybrid_search import hybrid_search
from app.services.profiler import update_user_profile
from app.utils.prompts import (
    build_allergy_context,
    build_decomposition_prompt,
    build_evaluation_prompt,
    build_user_context,
)

logger = logging.getLogger(__name__)

_allergy_guard = AllergyGuard()

# Safe fallback payload for any unrecoverable error
_FALLBACK_PAYLOAD = GenerativeUIPayload(
    ui_type="text",
    message=(
        "I'm having trouble right now — try rephrasing your request."
    ),
)


async def orchestrate(
    uid: UUID,
    message: str,
    history: list[ChatMessage],
    db: AsyncSession,
) -> AsyncIterator[str]:
    """
    Execute the 5-step reasoning loop and stream Server-Sent Events.

    Yields SSE-formatted strings:
      {"event": "thinking", "data": {...}}  (multiple)
      {"event": "result",   "data": <GenerativeUIPayload>}

    AllergyGuard failures return a safe error payload — never unguarded results.
    """

    async def _yield_thinking(step: str, **kwargs: Any) -> str:
        data = {"step": step, **kwargs}
        return f'{{"event": "thinking", "data": {json.dumps(data)}}}\n\n'

    # ── Step 1: Context retrieval ────────────────────────────────────────────
    yield await _yield_thinking("decomposing_query")

    result = await db.execute(
        text(
            "SELECT preferences, allergies, allergy_flags, dietary_flags, vibe_tags "
            "FROM users WHERE uid = :uid"
        ),
        {"uid": str(uid)},
    )
    row = result.fetchone()
    if not row:
        yield f'{{"event": "result", "data": {_FALLBACK_PAYLOAD.model_dump_json()}}}\n\n'
        return

    preferences = row.preferences or {}
    allergies = row.allergies or {}
    user_context = build_user_context(preferences)
    allergy_context = build_allergy_context(allergies)

    history_dicts = [{"role": m.role, "content": m.content} for m in history]

    # ── Step 2: Query decomposition [Gemma #1] ───────────────────────────────
    decomp_prompt = build_decomposition_prompt(
        message=message,
        user_context=user_context,
        history=history_dicts,
        allergy_context=allergy_context,
    )

    try:
        decomp: dict[str, Any] = await call_gemma_json(decomp_prompt)
    except GemmaError:
        yield f'{{"event": "result", "data": {_FALLBACK_PAYLOAD.model_dump_json()}}}\n\n'
        return

    intent = decomp.get("intent", "find_restaurant")
    sql_filters = decomp.get("sql_filters", {})
    vector_query = decomp.get("vector_query", message)
    ui_preference = decomp.get("ui_preference", "restaurant_list")
    needs_clarification = decomp.get("needs_clarification", False)
    clarification_question = decomp.get("clarification_question")

    # Ensure anaphylactic allergens are always excluded at SQL level
    anaphylactic = [
        a for a in allergies.get("confirmed", [])
        if allergies.get("severity", {}).get(a) == "anaphylactic"
    ]
    existing_excludes = sql_filters.get("exclude_allergens", [])
    sql_filters["exclude_allergens"] = list(set(existing_excludes + anaphylactic))

    # Handle clarification intent
    if needs_clarification and clarification_question:
        payload = GenerativeUIPayload(
            ui_type="text",
            message=clarification_question,
        )
        yield f'{{"event": "result", "data": {payload.model_dump_json()}}}\n\n'
        return

    yield await _yield_thinking("searching", filters=sql_filters)

    # ── Step 3: Hybrid search ────────────────────────────────────────────────
    candidates: list[RestaurantResult] = await hybrid_search(
        db=db,
        sql_filters=sql_filters,
        vector_query=vector_query,
        limit=15,
    )

    if not candidates:
        payload = GenerativeUIPayload(
            ui_type="text",
            message=(
                "I couldn't find any restaurants matching your request. "
                "Try broadening your search — different area, cuisine, or price range?"
            ),
        )
        yield f'{{"event": "result", "data": {payload.model_dump_json()}}}\n\n'
        return

    yield await _yield_thinking("evaluating", count=len(candidates))

    # ── Step 4: Evaluation loop [Gemma #2] ───────────────────────────────────
    top_candidates = candidates[:10]
    restaurants_json = json.dumps(
        [
            {
                "id": r.id,
                "name": r.name,
                "area": r.area,
                "price_tier": r.price_tier,
                "rating": r.rating,
                "cuisine_types": r.cuisine_types,
                "meta": r.meta,
            }
            for r in top_candidates
        ]
    )

    eval_prompt = build_evaluation_prompt(
        message=message,
        user_context=user_context,
        restaurants_json=restaurants_json,
        allergy_context=allergy_context,
    )

    try:
        scores_list: list[dict[str, Any]] = await call_gemma_json(eval_prompt)
    except GemmaError:
        scores_list = []

    # Map scores back to candidates
    scores_map: dict[int, dict[str, float]] = {}
    if isinstance(scores_list, list):
        for item in scores_list:
            if isinstance(item, dict) and "id" in item:
                scores_map[int(item["id"])] = item

    scored: list[RestaurantResult] = []
    for r in top_candidates:
        s = scores_map.get(r.id, {})
        updated = r.model_copy(
            update={
                "scores": RadarScores(
                    romance=float(s.get("romance", 0)),
                    noise_level=float(s.get("noise_level", 0)),
                    food_quality=float(s.get("food_quality", 0)),
                    vegan_options=float(s.get("vegan_options", 0)),
                    value_for_money=float(s.get("value_for_money", 0)),
                )
            }
        )
        scored.append(updated)

    # Sort by composite score descending
    def _composite(r: RestaurantResult) -> float:
        if not r.scores:
            return 0.0
        s = r.scores
        return (s.romance + s.food_quality + s.value_for_money + s.vegan_options) / 4

    scored.sort(key=_composite, reverse=True)
    top_results = scored[:5]

    yield await _yield_thinking("checking_allergies")

    # ── Step 5: AllergyGuard ─────────────────────────────────────────────────
    try:
        allergy_result: AllergyCheckResult = _allergy_guard.check(
            restaurants=top_results,
            user_allergies=allergies,
        )
    except Exception as exc:
        # AllergyGuard failure must never silently pass
        logger.error("AllergyGuard raised an exception: %s", exc)
        yield (
            f'{{"event": "result", "data": '
            f'{{"ui_type": "text", "message": '
            f'"I encountered a safety check error. Please try again.", '
            f'"restaurants": [], "flagged_restaurants": [], '
            f'"has_allergy_warnings": false}}}}\n\n'
        )
        return

    # ── Step 6: Response construction ────────────────────────────────────────
    has_warnings = allergy_result.has_any_warnings
    message_text = _build_response_message(
        message, allergy_result, ui_preference
    )

    payload = GenerativeUIPayload(
        ui_type=ui_preference if ui_preference in {
            "restaurant_list", "radar_comparison", "map_view", "text"
        } else "restaurant_list",
        message=message_text,
        restaurants=allergy_result.safe_restaurants,
        flagged_restaurants=allergy_result.flagged_restaurants,
        has_allergy_warnings=has_warnings,
    )

    yield f'{{"event": "result", "data": {payload.model_dump_json()}}}\n\n'

    # ── Fire-and-forget: save interaction + update profile ───────────────────
    # Use fresh sessions — the request session may close after streaming ends.
    restaurant_ids = [r.id for r in (allergy_result.safe_restaurants + allergy_result.flagged_restaurants)]
    allergens_flagged: list[str] = []
    for r in allergy_result.safe_restaurants + allergy_result.flagged_restaurants:
        for w in r.allergy_warnings:
            if w.allergen not in allergens_flagged:
                allergens_flagged.append(w.allergen)

    asyncio.create_task(_save_interaction(
        uid=uid,
        message=message,
        payload=payload,
        restaurant_ids=restaurant_ids,
        allergens_flagged=allergens_flagged,
        has_warnings=has_warnings,
    ))
    asyncio.create_task(_run_profiler(
        uid=uid,
        message=message,
        payload_dict=payload.model_dump(),
    ))


async def _save_interaction(
    uid: UUID,
    message: str,
    payload: GenerativeUIPayload,
    restaurant_ids: list[int],
    allergens_flagged: list[str],
    has_warnings: bool,
) -> None:
    """Persist the interaction record using a fresh session. Never raises."""
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO interactions
                        (uid, user_query, agent_response, ui_type, restaurant_ids,
                         allergy_warnings_shown, allergens_flagged)
                    VALUES
                        (:uid, :query, :response, :ui_type, :restaurant_ids,
                         :warnings_shown, :allergens_flagged)
                """),
                {
                    "uid": str(uid),
                    "query": message,
                    "response": payload.model_dump(),
                    "ui_type": payload.ui_type,
                    "restaurant_ids": restaurant_ids,
                    "warnings_shown": has_warnings,
                    "allergens_flagged": allergens_flagged,
                },
            )
            await db.commit()
    except Exception as exc:
        logger.error("Failed to save interaction for user %s: %s", uid, exc)


async def _run_profiler(uid: UUID, message: str, payload_dict: dict) -> None:
    """Run the profiler in a fresh session. Never raises."""
    try:
        async with AsyncSessionLocal() as db:
            await update_user_profile(
                uid=uid, message=message, agent_response=payload_dict, db=db
            )
    except Exception as exc:
        logger.error("Profiler wrapper failed for user %s: %s", uid, exc)


def _build_response_message(
    user_message: str,
    result: AllergyCheckResult,
    ui_type: str,
) -> str:
    """Build a natural-language message to accompany the Generative UI payload."""
    total = len(result.safe_restaurants) + len(result.flagged_restaurants)
    safe_count = len(result.safe_restaurants)

    if total == 0:
        return (
            "I couldn't find any restaurants that match your request. "
            "Try a different area, cuisine, or price range?"
        )

    base = f"I found {total} restaurant{'s' if total != 1 else ''} for you!"

    if result.flagged_restaurants:
        flagged_count = len(result.flagged_restaurants)
        base += (
            f" {flagged_count} ha{'s' if flagged_count == 1 else 've'} a high-risk "
            "allergy note — I've flagged it clearly at the bottom so you can decide."
        )
    elif result.has_any_warnings:
        base += " I've noted allergy information for some options — check the warnings before visiting."

    return base
