"""
Recommendation service — personalised restaurant feed, generated algorithmically
and enriched with a single LLM batch call.

Pipeline:
  1. Fetch user profile from DB
  2. Pull top-50 candidate restaurants by rating (hard anaphylactic SQL filter)
  3. Run FitScorer on all 50 candidates (pure Python, no LLM)
  4. Sort by fit_score DESC, take top `limit`
  5. Run AllergyGuard on selected candidates
  6. Batch LLM call: consolidated_review for all selected restaurants at once
  7. Assemble and cache RecommendationPayload

Caching:
  Key:  sha256(uid + date.today().isoformat())  — naturally expires at midnight
  TTL:  86400 s (24 h)
  Size: 1000 entries
  Bypass: refresh=True deletes the key before computing
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from cachetools import TTLCache
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.schemas.recommendation import (
    AllergySummary,
    ExpandedDetail,
    ExpandedDetailResponse,
    FitTag,
    Highlight,
    AllergyDetail,
    RecommendationItem,
    RecommendationPayload,
    UserProfile,
)
from app.schemas.restaurant import RadarScores, RestaurantResult
from app.services.allergy_guard import AllergyGuard
from app.services.fit_scorer import FitScorer
from app.services.gemma import GemmaError, call_gemma_json
from app.utils.prompts import (
    build_allergy_context,
    build_expand_detail_prompt,
    build_fit_explanation_prompt,
    build_user_context,
)

logger = logging.getLogger(__name__)

# ── Module-level singletons ────────────────────────────────────────────────────

_allergy_guard = AllergyGuard()
_fit_scorer = FitScorer()

# Cache: uid+date → RecommendationPayload JSON string
_cache_recommendations: TTLCache = TTLCache(maxsize=1_000, ttl=86_400)

# ── Cache key ──────────────────────────────────────────────────────────────────


def _rec_cache_key(uid: UUID) -> str:
    """Daily cache key — changes at midnight, making yesterday's cache stale."""
    raw = f"{uid}:{date.today().isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


# ── Main pipeline ──────────────────────────────────────────────────────────────


async def get_recommendations(
    uid: UUID,
    db: AsyncSession,
    limit: int = 10,
    refresh: bool = False,
) -> RecommendationPayload:
    """
    Build and return a RecommendationPayload for the user.

    Synchronous JSON response — not SSE.
    Results are cached per (uid, date). Pass refresh=True to force recompute.
    """
    limit = min(limit, 25)
    cache_key = _rec_cache_key(uid)

    # Cache bypass
    if refresh and cache_key in _cache_recommendations:
        del _cache_recommendations[cache_key]
        logger.debug("Recommendation cache INVALIDATED (uid=%s)", uid)

    # Cache hit
    if cache_key in _cache_recommendations:
        logger.debug("Recommendation cache HIT (uid=%s)", uid)
        cached_json = _cache_recommendations[cache_key]
        return RecommendationPayload.model_validate_json(cached_json)

    # ── Step 1: Fetch user profile ─────────────────────────────────────────────
    profile = await _fetch_user_profile(uid, db)

    # ── Step 2: Candidate retrieval (top 50 by rating, anaphylactic hard-filter) ─
    candidates = await _fetch_candidates(profile, db)

    if not candidates:
        payload = RecommendationPayload(
            uid=str(uid),
            generated_at=datetime.now(timezone.utc),
            recommendations=[],
        )
        _cache_recommendations[cache_key] = payload.model_dump_json()
        return payload

    # ── Step 3: Algorithmic scoring (FitScorer — no LLM) ──────────────────────
    scored: list[tuple[RestaurantResult, int, list[FitTag]]] = []
    for restaurant in candidates:
        result = _fit_scorer.score(restaurant, profile)
        scored.append((restaurant, result.score, result.fit_tags))

    # ── Step 4: Sort by fit_score DESC, take top `limit` ──────────────────────
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = scored[:limit]

    selected_restaurants = [r for r, _, _ in selected]

    # ── Step 5: AllergyGuard on selected candidates ────────────────────────────
    allergy_result = _allergy_guard.check(selected_restaurants, profile.allergies)

    # Build lookup for annotated restaurants keyed by id
    annotated_map: dict[int, RestaurantResult] = {}
    for r in allergy_result.safe_restaurants + allergy_result.flagged_restaurants:
        annotated_map[r.id] = r

    # ── Step 6: Batch LLM call for consolidated_review ────────────────────────
    review_map: dict[int, str] = await _batch_fetch_reviews(
        selected_restaurants, profile
    )

    # ── Step 7: Assemble RecommendationPayload ────────────────────────────────
    items: list[RecommendationItem] = []
    for rank, (restaurant, fit_score, fit_tags) in enumerate(selected, start=1):
        annotated = annotated_map.get(restaurant.id, restaurant)
        consolidated = review_map.get(restaurant.id, "")[:160]

        # Allergy summary for collapsed card
        allergy_summary = AllergySummary(
            is_safe=annotated.allergy_safe,
            warnings=annotated.allergy_warnings,
        )

        items.append(
            RecommendationItem(
                rank=rank,
                restaurant=annotated,
                fit_score=fit_score,
                fit_tags=fit_tags,
                consolidated_review=consolidated,
                allergy_summary=allergy_summary,
                expanded_detail=None,
            )
        )

    payload = RecommendationPayload(
        uid=str(uid),
        generated_at=datetime.now(timezone.utc),
        recommendations=items,
    )

    # Store in cache
    _cache_recommendations[cache_key] = payload.model_dump_json()
    logger.info(
        "Recommendations generated for uid=%s: %d items (limit=%d)",
        uid, len(items), limit,
    )

    return payload


# ── Expand endpoint pipeline ───────────────────────────────────────────────────


async def get_expanded_detail(
    uid: UUID,
    restaurant_id: int,
    db: AsyncSession,
) -> ExpandedDetailResponse:
    """
    Generate the full ExpandedDetail for a single restaurant.
    Always freshly generated — not cached.
    Uses its own fresh DB session semantics (caller passes a fresh session).
    """
    # Fetch restaurant + its reviews
    restaurant, review_texts = await _fetch_restaurant_and_reviews(
        restaurant_id, db
    )

    # Fetch user profile
    profile = await _fetch_user_profile(uid, db)

    # Build prompt and call LLM
    user_context = build_user_context(profile.preferences)
    allergy_context = build_allergy_context(profile.allergies)

    prompt = build_expand_detail_prompt(
        restaurant=restaurant.model_dump(),
        reviews=review_texts[:10],
        user_context=user_context,
        allergy_context=allergy_context,
    )

    try:
        raw: dict[str, Any] = await call_gemma_json(prompt)
    except GemmaError:
        logger.warning("LLM failed for expand (restaurant_id=%d) — using fallback", restaurant_id)
        raw = _fallback_expanded_detail(restaurant)

    # Parse radar scores (5.0 neutral fallback per-field)
    raw_radar = raw.get("radar_scores") or {}
    radar = RadarScores(
        romance=float(raw_radar.get("romance", 5.0)),
        noise_level=float(raw_radar.get("noise_level", 5.0)),
        food_quality=float(raw_radar.get("food_quality", 5.0)),
        vegan_options=float(raw_radar.get("vegan_options", 5.0)),
        value_for_money=float(raw_radar.get("value_for_money", 5.0)),
    )

    # Parse highlights
    raw_highlights = raw.get("highlights") or []
    highlights = [
        Highlight(
            emoji=str(h.get("emoji", "•")),
            text=str(h.get("text", "")),
        )
        for h in raw_highlights
        if isinstance(h, dict)
    ][:5]

    # Run AllergyGuard on this single restaurant for the detail view
    annotated_result = _allergy_guard.check([restaurant], profile.allergies)
    annotated = (
        annotated_result.safe_restaurants[0]
        if annotated_result.safe_restaurants
        else annotated_result.flagged_restaurants[0]
        if annotated_result.flagged_restaurants
        else restaurant
    )

    allergy_detail = AllergyDetail(
        is_safe=annotated.allergy_safe,
        confidence=annotated.allergen_confidence,
        warnings=annotated.allergy_warnings,
        safe_note=(
            "No allergens detected matching your profile."
            if annotated.allergy_safe
            else None
        ),
    )

    expanded = ExpandedDetail(
        review_summary=str(raw.get("review_summary", "No review summary available.")),
        highlights=highlights,
        crowd_profile=str(raw.get("crowd_profile", "Information not available.")),
        best_for=[str(x) for x in (raw.get("best_for") or [])[:4]],
        avoid_if=[str(x) for x in (raw.get("avoid_if") or [])[:3]],
        radar_scores=radar,
        why_fit_paragraph=str(raw.get("why_fit_paragraph", "")),
        allergy_detail=allergy_detail,
    )

    return ExpandedDetailResponse(
        restaurant_id=restaurant_id,
        expanded_detail=expanded,
    )


# ── Pre-warming ────────────────────────────────────────────────────────────────


async def prewarm_recommendations(uid: UUID) -> None:
    """
    Fire-and-forget: regenerate recommendations and write to cache.
    Called after a successful profiler update.
    Opens its own session — never reuses the profiler session.
    Never raises.
    """
    try:
        async with AsyncSessionLocal() as db:
            await get_recommendations(uid=uid, db=db, limit=10, refresh=True)
            logger.debug("Recommendations pre-warmed for uid=%s", uid)
    except Exception as exc:
        logger.warning("prewarm_recommendations failed for uid=%s: %s", uid, exc)


# ── DB helpers ─────────────────────────────────────────────────────────────────


async def _fetch_user_profile(uid: UUID, db: AsyncSession) -> UserProfile:
    """Fetch and return a flattened UserProfile from the users table."""
    result = await db.execute(
        text(
            "SELECT preferences, allergies, allergy_flags, dietary_flags, "
            "vibe_tags, preferred_price_tiers "
            "FROM users WHERE uid = :uid"
        ),
        {"uid": str(uid)},
    )
    row = result.fetchone()
    if not row:
        return UserProfile()

    preferences: dict = dict(row.preferences or {})
    allergies: dict = dict(row.allergies or {})

    return UserProfile(
        preferences=preferences,
        allergies=allergies,
        allergy_flags=list(row.allergy_flags or []),
        dietary_flags=list(row.dietary_flags or []),
        vibe_tags=list(row.vibe_tags or []),
        preferred_price_tiers=list(row.preferred_price_tiers or []),
        cuisine_affinity=list(preferences.get("cuisine_affinity", [])),
        cuisine_aversion=list(preferences.get("cuisine_aversion", [])),
    )


async def _fetch_candidates(
    profile: UserProfile,
    db: AsyncSession,
    pool_size: int = 50,
) -> list[RestaurantResult]:
    """
    Fetch top pool_size restaurants by rating.
    Hard SQL filter: NOT (known_allergens && allergy_flags) for anaphylactic safety.
    """
    anaphylactic_allergens: list[str] = [
        allergen
        for allergen in profile.allergies.get("confirmed", [])
        if profile.allergies.get("severity", {}).get(allergen) == "anaphylactic"
    ]

    # Build query
    if anaphylactic_allergens:
        sql = text("""
            SELECT
                id, name, url, address, area, city,
                cuisine_types, price_tier, cost_for_two,
                rating, votes, lat, lng,
                known_allergens, allergen_confidence, meta
            FROM restaurants
            WHERE is_active = TRUE
              AND NOT (known_allergens && :exclude_allergens)
            ORDER BY rating DESC NULLS LAST
            LIMIT :limit
        """)
        params: dict[str, Any] = {
            "exclude_allergens": anaphylactic_allergens,
            "limit": pool_size,
        }
    else:
        sql = text("""
            SELECT
                id, name, url, address, area, city,
                cuisine_types, price_tier, cost_for_two,
                rating, votes, lat, lng,
                known_allergens, allergen_confidence, meta
            FROM restaurants
            WHERE is_active = TRUE
            ORDER BY rating DESC NULLS LAST
            LIMIT :limit
        """)
        params = {"limit": pool_size}

    result = await db.execute(sql, params)
    rows = result.fetchall()

    restaurants: list[RestaurantResult] = []
    for row in rows:
        restaurants.append(
            RestaurantResult(
                id=row.id,
                name=row.name,
                url=row.url,
                address=row.address,
                area=row.area,
                price_tier=row.price_tier,
                rating=float(row.rating) if row.rating is not None else None,
                votes=row.votes or 0,
                cuisine_types=list(row.cuisine_types or []),
                lat=row.lat,
                lng=row.lng,
                known_allergens=list(row.known_allergens or []),
                allergen_confidence=row.allergen_confidence or "low",
                meta=dict(row.meta or {}),
            )
        )
    return restaurants


async def _fetch_restaurant_and_reviews(
    restaurant_id: int,
    db: AsyncSession,
) -> tuple[RestaurantResult, list[str]]:
    """Fetch a single restaurant and up to 10 of its review texts."""
    r_result = await db.execute(
        text("""
            SELECT
                id, name, url, address, area, city,
                cuisine_types, price_tier, cost_for_two,
                rating, votes, lat, lng,
                known_allergens, allergen_confidence, meta
            FROM restaurants
            WHERE id = :id AND is_active = TRUE
        """),
        {"id": restaurant_id},
    )
    row = r_result.fetchone()
    if not row:
        raise ValueError(f"Restaurant {restaurant_id} not found")

    restaurant = RestaurantResult(
        id=row.id,
        name=row.name,
        url=row.url,
        address=row.address,
        area=row.area,
        price_tier=row.price_tier,
        rating=float(row.rating) if row.rating is not None else None,
        votes=row.votes or 0,
        cuisine_types=list(row.cuisine_types or []),
        lat=row.lat,
        lng=row.lng,
        known_allergens=list(row.known_allergens or []),
        allergen_confidence=row.allergen_confidence or "low",
        meta=dict(row.meta or {}),
    )

    rv_result = await db.execute(
        text("""
            SELECT text FROM reviews
            WHERE restaurant_id = :id AND text IS NOT NULL
            ORDER BY id DESC
            LIMIT 10
        """),
        {"id": restaurant_id},
    )
    review_texts = [r.text for r in rv_result.fetchall() if r.text]

    return restaurant, review_texts


# ── LLM helpers ────────────────────────────────────────────────────────────────


async def _batch_fetch_reviews(
    restaurants: list[RestaurantResult],
    profile: UserProfile,
) -> dict[int, str]:
    """
    One LLM call for all selected restaurants → dict[restaurant_id, consolidated_review].
    Falls back to empty strings on LLM failure.
    """
    if not restaurants:
        return {}

    user_context = build_user_context(profile.preferences)
    allergy_context = build_allergy_context(profile.allergies)

    restaurants_dicts = [
        {
            "id": r.id,
            "name": r.name,
            "cuisine_types": r.cuisine_types,
            "area": r.area,
            "price_tier": r.price_tier,
            "rating": r.rating,
        }
        for r in restaurants
    ]

    prompt = build_fit_explanation_prompt(
        restaurants=restaurants_dicts,
        user_context=user_context,
        allergy_context=allergy_context,
    )

    try:
        raw_list: list[dict[str, Any]] = await call_gemma_json(prompt)
        if not isinstance(raw_list, list):
            raise GemmaError("fit_explanation prompt returned non-list")
    except GemmaError as exc:
        logger.warning("Batch fit explanation LLM call failed: %s", exc)
        return {}

    review_map: dict[int, str] = {}
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        rid = item.get("restaurant_id")
        review = item.get("consolidated_review", "")
        if rid is not None and review:
            review_map[int(rid)] = str(review).strip()[:160]

    return review_map


def _fallback_expanded_detail(restaurant: RestaurantResult) -> dict[str, Any]:
    """Minimal fallback when LLM fails for /expand."""
    return {
        "review_summary": f"{restaurant.name} is a restaurant in {restaurant.area or 'Bangalore'}.",
        "highlights": [
            {"emoji": "🍽️", "text": f"Serves {', '.join(restaurant.cuisine_types[:2]) or 'a variety of cuisines'}"},
            {"emoji": "⭐", "text": f"Rated {restaurant.rating or 'N/A'} on Zomato"},
        ],
        "crowd_profile": "Information not available for this restaurant.",
        "best_for": ["Dining out"],
        "avoid_if": [],
        "radar_scores": {
            "romance": 5.0,
            "noise_level": 5.0,
            "food_quality": 5.0,
            "vegan_options": 5.0,
            "value_for_money": 5.0,
        },
        "why_fit_paragraph": "This restaurant matches your general dining preferences.",
        "allergy_detail": {
            "is_safe": True,
            "confidence": restaurant.allergen_confidence,
            "warnings": [],
            "safe_note": "Allergen data may be limited.",
        },
    }
