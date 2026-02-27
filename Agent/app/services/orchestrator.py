"""
Orchestrator — ReAct (Reasoning + Acting) agentic loop powering every chat turn.

Each request runs through a while-loop (max 5 iterations) where a Gemma planner
chooses one of four tools on every iteration:

  search_restaurants   → hybrid SQL + vector search
  evaluate_candidates  → LLM-based 5-dimension scoring
  ask_clarification    → short-circuit with a question for the user
  final_response       → AllergyGuard + GenerativeUIPayload → SSE result event

In-memory caching (cachetools TTLCache) reduces LLM and DB calls for repeated
or near-identical queries:
  _cache_decomp  — first-iteration planner output (TTL 3600 s, maxsize 10,000)
  _cache_search  — hybrid search results        (TTL 1800 s, maxsize 5,000)

AllergyGuard always runs inside final_response — never cached, never skipped.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, AsyncIterator
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.schemas.chat import ChatMessage
from app.schemas.restaurant import GenerativeUIPayload, RadarScores, RestaurantResult
from app.services.allergy_guard import AllergyCheckResult, AllergyGuard
from app.services.gemma import GemmaError, call_gemma_json
from app.services.hybrid_search import hybrid_search
from app.services.profiler import update_user_profile
from app.utils.prompts import (
    build_allergy_context,
    build_evaluation_prompt,
    build_planner_prompt,
    build_user_context,
)

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 5

# Safe fallback payload for any unrecoverable error
_FALLBACK_PAYLOAD = GenerativeUIPayload(
    ui_type="text",
    message="I'm having trouble right now — try rephrasing your request.",
)

# ── Module-level singletons (instantiated once at import time) ─────────────────

_allergy_guard = AllergyGuard()

# Cache 1 — planner first-iteration output
# Key  : sha256(message + sorted_vibes + sorted_dietary)[:16]
# Value: dict — the raw plan returned by the planner on iteration 0
# TTL  : 3600 s   MaxSize: 10,000
_cache_decomp: TTLCache = TTLCache(maxsize=10_000, ttl=3600)

# Cache 2 — hybrid search results
# Key  : sha256(json.dumps(sql_filters, sort_keys=True) + vector_query)[:16]
# Value: JSON string — list[RestaurantResult.model_dump()]
# TTL  : 1800 s   MaxSize: 5,000
_cache_search: TTLCache = TTLCache(maxsize=5_000, ttl=1800)


# ── Cache key helpers ─────────────────────────────────────────────────────────

def _decomp_cache_key(
    message: str, vibe_tags: list[str], dietary_flags: list[str]
) -> str:
    raw = message + "".join(sorted(vibe_tags)) + "".join(sorted(dietary_flags))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _search_cache_key(sql_filters: dict[str, Any], vector_query: str) -> str:
    # Normalise list values so key is order-independent
    normalised: dict[str, Any] = {
        k: sorted(v) if isinstance(v, list) else v
        for k, v in sql_filters.items()
    }
    raw = json.dumps(normalised, sort_keys=True) + vector_query
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Anaphylactic hard SQL override ────────────────────────────────────────────

def _apply_anaphylactic_override(
    sql_filters: dict[str, Any],
    allergies: dict[str, Any],
) -> dict[str, Any]:
    """
    Always inject anaphylactic allergens into sql_filters.exclude_allergens
    before any DB query is run. Independent of planner output.
    """
    severity_map: dict[str, str] = allergies.get("severity", {})
    confirmed: list[str] = allergies.get("confirmed", [])
    anaphylactic = [a for a in confirmed if severity_map.get(a) == "anaphylactic"]
    existing = sql_filters.get("exclude_allergens", [])
    return {**sql_filters, "exclude_allergens": list(set(existing + anaphylactic))}


# ── Tool: search_restaurants (with _cache_search) ────────────────────────────

async def _tool_search_restaurants(
    sql_filters: dict[str, Any],
    vector_query: str,
    db: AsyncSession,
) -> tuple[list[RestaurantResult], bool]:
    """
    Run hybrid search. Returns (results, was_cache_hit).

    On a cache miss the results are serialised and stored.
    AllergyGuard is NOT called here — that happens in final_response only.
    """
    key = _search_cache_key(sql_filters, vector_query)
    cached = _cache_search.get(key)
    if cached is not None:
        logger.debug("Search cache HIT (key=%s)", key)
        raw: list[dict] = json.loads(cached)
        return [RestaurantResult.model_validate(r) for r in raw], True

    logger.debug("Search cache MISS (key=%s)", key)
    results = await hybrid_search(
        db=db,
        sql_filters=sql_filters,
        vector_query=vector_query,
        limit=15,
    )
    if results:
        _cache_search[key] = json.dumps([r.model_dump() for r in results])
    return results, False


# ── Tool: evaluate_candidates ────────────────────────────────────────────────

async def _tool_evaluate_candidates(
    candidates: list[RestaurantResult],
    message: str,
    user_context: str,
    allergy_context: str,
) -> list[RestaurantResult]:
    """Score top-10 candidates with Gemma and return sorted list."""
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

    scores_list: list[dict[str, Any]] = []
    try:
        scores_list = await call_gemma_json(eval_prompt)
    except GemmaError as exc:
        logger.warning(
            "evaluate_candidates: Gemma scoring failed — proceeding without scores: %s", exc
        )

    scores_map: dict[int, dict[str, float]] = {}
    if isinstance(scores_list, list):
        for item in scores_list:
            if isinstance(item, dict) and "id" in item:
                scores_map[int(item["id"])] = item

    scored: list[RestaurantResult] = []
    for r in top_candidates:
        s = scores_map.get(r.id, {})
        scored.append(
            r.model_copy(
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
        )

    def _composite(r: RestaurantResult) -> float:
        if not r.scores:
            return 0.0
        s = r.scores
        return (s.romance + s.food_quality + s.value_for_money + s.vegan_options) / 4

    scored.sort(key=_composite, reverse=True)
    return scored


# ── AllergyGuard + response builder (used by final_response tool) ─────────────

def _build_response_message(
    user_message: str,
    result: AllergyCheckResult,
    ui_type: str,
) -> str:
    total = len(result.safe_restaurants) + len(result.flagged_restaurants)
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
        base += (
            " I've noted allergy information for some options — "
            "check the warnings before visiting."
        )
    return base


def _run_allergy_guard_and_build_payload(
    candidates: list[RestaurantResult],
    allergies: dict[str, Any],
    message: str,
    ui_type: str,
) -> GenerativeUIPayload:
    """
    Run AllergyGuard and construct the GenerativeUIPayload.
    Always called per-user — never cached.
    """
    try:
        allergy_result: AllergyCheckResult = _allergy_guard.check(
            restaurants=candidates[:5],
            user_allergies=allergies,
        )
    except Exception as exc:
        logger.error("AllergyGuard raised an exception: %s", exc)
        return GenerativeUIPayload(
            ui_type="text",
            message="I encountered a safety check error. Please try again.",
            restaurants=[],
            flagged_restaurants=[],
            has_allergy_warnings=False,
        )

    valid_ui_types = {"restaurant_list", "radar_comparison", "map_view", "text"}
    safe_ui_type = ui_type if ui_type in valid_ui_types else "restaurant_list"
    message_text = _build_response_message(message, allergy_result, safe_ui_type)

    return GenerativeUIPayload(
        ui_type=safe_ui_type,
        message=message_text,
        restaurants=allergy_result.safe_restaurants,
        flagged_restaurants=allergy_result.flagged_restaurants,
        has_allergy_warnings=allergy_result.has_any_warnings,
    )


# ── Main orchestrate generator ────────────────────────────────────────────────

async def orchestrate(
    uid: UUID,
    message: str,
    history: list[ChatMessage],
    db: AsyncSession,
) -> AsyncIterator[str]:
    """
    Execute the ReAct agentic loop and stream Server-Sent Events.

    Yields SSE-formatted strings:
      {"event": "thinking", "data": {...}}                — reasoning progress
      {"event": "result",   "data": <GenerativeUIPayload>}  — final UI payload

    The loop runs for at most _MAX_ITERATIONS (5) before forcing a final_response.
    AllergyGuard always runs inside final_response — not cached, not skipped.
    Background tasks fire after the loop exits.
    """

    def _sse(event: str, data: Any) -> str:
        """Format a single SSE frame. data may be a dict or a pre-serialised JSON str."""
        payload = data if isinstance(data, str) else json.dumps(data)
        return f'{{"event": "{event}", "data": {payload}}}\n\n'

    # ── Step 1: User context retrieval (never cached) ─────────────────────────
    yield _sse("thinking", {"step": "fetching_context"})

    db_result = await db.execute(
        text(
            "SELECT preferences, allergies, allergy_flags, dietary_flags, vibe_tags "
            "FROM users WHERE uid = :uid"
        ),
        {"uid": str(uid)},
    )
    row = db_result.fetchone()
    if not row:
        yield _sse("result", _FALLBACK_PAYLOAD.model_dump_json())
        return

    preferences: dict[str, Any] = dict(row.preferences or {})
    allergies: dict[str, Any] = dict(row.allergies or {})
    dietary_flags: list[str] = list(row.dietary_flags or [])
    vibe_tags: list[str] = list(row.vibe_tags or [])

    user_context = build_user_context(preferences)
    allergy_context = build_allergy_context(allergies)
    history_dicts = [{"role": m.role, "content": m.content} for m in history]

    decomp_key = _decomp_cache_key(message, vibe_tags, dietary_flags)

    # ── Optional: local intent classifier ─────────────────────────────────────
    if settings.use_local_classifier:
        try:
            from app.services.local_ml import (  # noqa: PLC0415
                CASUAL_CHAT_CONFIDENCE_THRESHOLD,
                classify_intent,
            )
            intent_label, confidence = await classify_intent(message)
            if intent_label == "casual_chat" and confidence > CASUAL_CHAT_CONFIDENCE_THRESHOLD:
                logger.info(
                    "Intent classifier: casual_chat (%.2f) — short-circuiting loop.",
                    confidence,
                )
                short_circuit = GenerativeUIPayload(
                    ui_type="text",
                    message=(
                        "I'm Kairos, your restaurant recommendation assistant for Bangalore! "
                        "I'm best at helping you find the perfect place to eat. "
                        "What kind of restaurant are you looking for today?"
                    ),
                )
                yield _sse("result", short_circuit.model_dump_json())
                return
        except Exception as exc:
            logger.warning("Local intent classifier failed (skipping): %s", exc)

    # ── ReAct loop ─────────────────────────────────────────────────────────────
    observations: list[str] = []
    current_candidates: list[RestaurantResult] = []
    final_payload: GenerativeUIPayload | None = None
    iteration = 0

    while True:
        # ── Hard cap — check BEFORE planner call ──────────────────────────────
        if iteration >= _MAX_ITERATIONS:
            logger.warning(
                "ReAct loop hit max iterations (%d) without final_response — "
                "forcing final_response with available candidates.",
                _MAX_ITERATIONS,
            )
            if not current_candidates:
                final_payload = GenerativeUIPayload(
                    ui_type="text",
                    message=(
                        "I couldn't find any restaurants matching your request. "
                        "Try broadening your search — different area, cuisine, or price range?"
                    ),
                )
            else:
                yield _sse("thinking", {"step": "checking_allergies"})
                final_payload = _run_allergy_guard_and_build_payload(
                    current_candidates, allergies, message, "restaurant_list"
                )
            yield _sse("result", final_payload.model_dump_json())
            break

        # ── Planner (with first-iteration cache) ──────────────────────────────
        plan: dict[str, Any] | None = None
        if iteration == 0:
            cached_plan = _cache_decomp.get(decomp_key)
            if cached_plan is not None:
                logger.debug("Decomp cache HIT (key=%s)", decomp_key)
                plan = cached_plan

        if plan is None:
            planner_prompt = build_planner_prompt(
                user_context=user_context,
                allergy_context=allergy_context,
                history=history_dicts,
                message=message,
                observations=observations,
            )
            try:
                plan = await call_gemma_json(planner_prompt)
            except GemmaError as exc:
                logger.exception(
                    "Planner Gemma call failed (iter=%d): %s", iteration, exc
                )
                yield _sse("result", _FALLBACK_PAYLOAD.model_dump_json())
                return

            # Cache the first-iteration plan for identical future queries
            if iteration == 0:
                _cache_decomp[decomp_key] = plan
                logger.debug("Decomp cache SET (key=%s)", decomp_key)

        if not isinstance(plan, dict):
            logger.error(
                "Planner returned non-dict (iter=%d): %r", iteration, plan
            )
            yield _sse("result", _FALLBACK_PAYLOAD.model_dump_json())
            return

        thought: str = plan.get("thought", "")
        tool: str = plan.get("tool", "")
        tool_input: dict[str, Any] = plan.get("tool_input", {}) or {}

        # Emit planning thinking event (includes LLM thought for transparency)
        yield _sse(
            "thinking",
            {"step": "planning", "iteration": iteration + 1, "thought": thought},
        )

        # ── Tool dispatch ──────────────────────────────────────────────────────

        if tool == "search_restaurants":
            sql_filters: dict[str, Any] = dict(tool_input.get("sql_filters") or {})
            vector_query: str = tool_input.get("vector_query") or message

            # Anaphylactic hard-override — runs before every DB query
            sql_filters = _apply_anaphylactic_override(sql_filters, allergies)

            yield _sse("thinking", {"step": "searching", "filters": sql_filters})

            results, cache_hit = await _tool_search_restaurants(
                sql_filters, vector_query, db
            )

            # Optional local reranker (applied before handing off to evaluate)
            if settings.use_local_reranker and results:
                try:
                    from app.services.local_ml import rerank  # noqa: PLC0415

                    results = await rerank(message, results, top_k=10)
                    logger.debug(
                        "Local reranker applied — %d candidates.", len(results)
                    )
                except Exception as exc:
                    logger.warning("Local reranker failed (skipping): %s", exc)

            current_candidates = results
            hit_label = " (cache hit)" if cache_hit else ""
            obs_filters = json.dumps(sql_filters, default=str)
            observations.append(
                f"search_restaurants{hit_label}: found {len(results)} results "
                f"for filters={obs_filters}, vector_query={vector_query!r}."
            )
            if results:
                # ── Auto-evaluate and deliver ─────────────────────────────────
                # Prevent the planner from wasting remaining iterations by re-searching
                # with wider filters when we already have candidates.
                yield _sse("thinking", {"step": "evaluating", "count": len(results)})
                current_candidates = await _tool_evaluate_candidates(
                    current_candidates, message, user_context, allergy_context
                )
                yield _sse("thinking", {"step": "checking_allergies"})
                final_payload = _run_allergy_guard_and_build_payload(
                    current_candidates, allergies, message, "restaurant_list"
                )
                yield _sse("result", final_payload.model_dump_json())
                break
            else:
                observations.append(
                    "search_restaurants: 0 results — broaden filters on next iteration "
                    "(remove area constraint, lower price tier, drop cuisine filter)."
                )

        elif tool == "evaluate_candidates":
            if not current_candidates:
                observations.append(
                    "evaluate_candidates: skipped — no candidates available yet. "
                    "Call search_restaurants first."
                )
            else:
                yield _sse(
                    "thinking",
                    {"step": "evaluating", "count": len(current_candidates)},
                )
                current_candidates = await _tool_evaluate_candidates(
                    current_candidates, message, user_context, allergy_context
                )
                top_name = (
                    current_candidates[0].name if current_candidates else "none"
                )
                observations.append(
                    f"evaluate_candidates: scored {len(current_candidates)} candidates. "
                    f"Top: {top_name!r}."
                )

        elif tool == "ask_clarification":
            question: str = (
                tool_input.get("question")
                or "Could you please clarify your request?"
            )
            final_payload = GenerativeUIPayload(ui_type="text", message=question)
            yield _sse("result", final_payload.model_dump_json())
            break

        elif tool == "final_response":
            ui_type_req: str = tool_input.get("ui_type") or "restaurant_list"
            if not current_candidates:
                final_payload = GenerativeUIPayload(
                    ui_type="text",
                    message=(
                        "I couldn't find any restaurants matching your request. "
                        "Try broadening your search — different area, cuisine, or price range?"
                    ),
                )
                yield _sse("result", final_payload.model_dump_json())
            else:
                yield _sse("thinking", {"step": "checking_allergies"})
                final_payload = _run_allergy_guard_and_build_payload(
                    current_candidates, allergies, message, ui_type_req
                )
                yield _sse("result", final_payload.model_dump_json())
            break

        else:
            # Unknown tool — force final_response to avoid infinite loop
            logger.warning(
                "Planner returned unknown tool %r (iter=%d) — forcing final_response.",
                tool,
                iteration,
            )
            if current_candidates:
                yield _sse("thinking", {"step": "checking_allergies"})
                final_payload = _run_allergy_guard_and_build_payload(
                    current_candidates, allergies, message, "restaurant_list"
                )
                yield _sse("result", final_payload.model_dump_json())
            else:
                final_payload = _FALLBACK_PAYLOAD
                yield _sse("result", final_payload.model_dump_json())
            break

        iteration += 1

    # ── Fire-and-forget background tasks ──────────────────────────────────────
    if final_payload is None:
        final_payload = _FALLBACK_PAYLOAD

    restaurant_ids: list[int] = [
        r.id
        for r in (final_payload.restaurants or [])
        + (final_payload.flagged_restaurants or [])
    ]
    allergens_flagged: list[str] = []
    for r in (final_payload.restaurants or []) + (final_payload.flagged_restaurants or []):
        for w in r.allergy_warnings:
            if w.allergen not in allergens_flagged:
                allergens_flagged.append(w.allergen)

    asyncio.create_task(
        _save_interaction(
            uid=uid,
            message=message,
            payload=final_payload,
            restaurant_ids=restaurant_ids,
            allergens_flagged=allergens_flagged,
            has_warnings=final_payload.has_allergy_warnings,
        )
    )
    asyncio.create_task(
        _run_profiler(
            uid=uid,
            message=message,
            payload_dict=final_payload.model_dump(),
        )
    )


# ── Background task helpers ───────────────────────────────────────────────────

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
                    "response": json.dumps(payload.model_dump()),  # JSONB needs serialized text
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
