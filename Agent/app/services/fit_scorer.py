"""
FitScorer — pure algorithmic scorer.
No LLM calls. No DB calls. Scores a restaurant against a user profile.

Scoring breakdown (total 100 pts):
  Cuisine affinity  — 30 pts
  Vibe match        — 25 pts
  Price comfort     — 20 pts
  Dietary compat    — 15 pts
  Allergy safety    — 10 pts
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.recommendation import FitTag, UserProfile
from app.schemas.restaurant import RestaurantResult

# Price tier ordering for adjacency scoring
_TIER_ORDER: list[str] = ["$", "$$", "$$$", "$$$$"]


@dataclass
class FitResult:
    """Output of FitScorer.score()."""

    score: int               # 0–100
    fit_tags: list[FitTag]   # up to 4 items, highest-value dimensions first


class FitScorer:
    """
    Pure Python scorer. Receives pre-fetched data and returns a FitResult.
    Runs on up to 50 candidates per request — must stay fast.
    """

    def score(
        self,
        restaurant: RestaurantResult,
        profile: UserProfile,
    ) -> FitResult:
        """
        Score a single restaurant against the user profile.
        Returns a FitResult with score 0–100 and up to 4 FitTags.
        """
        # Each dimension returns (points_earned, FitTag | None)
        cuisine_pts, cuisine_tag = self._score_cuisine(restaurant, profile)
        vibe_pts, vibe_tag = self._score_vibe(restaurant, profile)
        price_pts, price_tag = self._score_price(restaurant, profile)
        dietary_pts, dietary_tag = self._score_dietary(restaurant, profile)
        allergy_pts, allergy_tag = self._score_allergy(restaurant)

        total = cuisine_pts + vibe_pts + price_pts + dietary_pts + allergy_pts
        total = max(0, min(100, total))  # clamp to valid range

        # Collect (points, tag) pairs, sort by points desc, take top 4 non-None
        dimension_scores: list[tuple[int, FitTag | None]] = [
            (cuisine_pts, cuisine_tag),
            (vibe_pts, vibe_tag),
            (price_pts, price_tag),
            (dietary_pts, dietary_tag),
            (allergy_pts, allergy_tag),
        ]
        dimension_scores.sort(key=lambda x: x[0], reverse=True)
        fit_tags: list[FitTag] = [
            tag for _, tag in dimension_scores if tag is not None
        ][:4]

        return FitResult(score=total, fit_tags=fit_tags)

    # ── Dimension scorers ──────────────────────────────────────────────────────

    def _score_cuisine(
        self,
        restaurant: RestaurantResult,
        profile: UserProfile,
    ) -> tuple[int, FitTag | None]:
        """Up to 30 pts. -10 for aversion match."""
        cuisine_types = {c.lower() for c in (restaurant.cuisine_types or [])}
        affinity = {c.lower() for c in (profile.cuisine_affinity or [])}
        aversion = {c.lower() for c in (profile.cuisine_aversion or [])}

        if not affinity and not aversion:
            return 0, None

        # Aversion penalty — applied first
        if cuisine_types & aversion:
            return -10, None

        if not affinity:
            return 0, None

        overlap = cuisine_types & affinity
        if not overlap:
            return 0, None

        # Full overlap: all restaurant cuisines match ≥1 affinity type
        if len(overlap) >= len(cuisine_types):
            pts = 30
        else:
            # Partial: at least 1 match
            pts = 15

        first_match = next(iter(overlap))
        tag = FitTag(
            label=f"Matches your {first_match.title()} preference",
            type="cuisine",
        )
        return pts, tag

    def _score_vibe(
        self,
        restaurant: RestaurantResult,
        profile: UserProfile,
    ) -> tuple[int, FitTag | None]:
        """Up to 25 pts. +5 per overlapping vibe, capped at 25."""
        user_vibes = {v.lower() for v in (profile.vibe_tags or [])}
        if not user_vibes:
            return 0, None

        # Restaurant vibes come from meta dict
        meta = restaurant.meta or {}
        restaurant_vibes_raw: list[str] = []
        # Accept several possible keys that ingest might use
        for key in ("vibes", "vibe_tags", "atmosphere", "tags"):
            val = meta.get(key)
            if isinstance(val, list):
                restaurant_vibes_raw.extend(val)
            elif isinstance(val, str):
                restaurant_vibes_raw.append(val)

        restaurant_vibes = {v.lower() for v in restaurant_vibes_raw}
        overlap = user_vibes & restaurant_vibes

        if not overlap:
            return 0, None

        pts = min(25, len(overlap) * 5)
        first_vibe = next(iter(overlap))
        tag = FitTag(
            label=f"Known for {first_vibe} — your top vibe tag",
            type="vibe",
        )
        return pts, tag

    def _score_price(
        self,
        restaurant: RestaurantResult,
        profile: UserProfile,
    ) -> tuple[int, FitTag | None]:
        """Up to 20 pts. +20 exact, +10 one tier adjacent, 0 otherwise."""
        preferred = set(profile.preferred_price_tiers or [])
        if not preferred:
            # Also check price_comfort from preferences JSONB
            preferred = set(profile.preferences.get("price_comfort", []))

        if not preferred or not restaurant.price_tier:
            return 0, None

        tier = restaurant.price_tier

        if tier in preferred:
            tag = FitTag(
                label=f"Within your {tier} comfort zone",
                type="price",
            )
            return 20, tag

        # Check adjacency
        try:
            r_idx = _TIER_ORDER.index(tier)
        except ValueError:
            return 0, None

        for p_tier in preferred:
            try:
                p_idx = _TIER_ORDER.index(p_tier)
                if abs(r_idx - p_idx) == 1:
                    return 10, None  # adjacent — partial credit, no tag
            except ValueError:
                continue

        return 0, None

    def _score_dietary(
        self,
        restaurant: RestaurantResult,
        profile: UserProfile,
    ) -> tuple[int, FitTag | None]:
        """Up to 15 pts. +5 per matching dietary flag, capped at 15."""
        user_dietary = {d.lower() for d in (profile.dietary_flags or [])}
        if not user_dietary:
            return 0, None

        meta = restaurant.meta or {}
        # Accept several possible meta keys for dietary flags
        restaurant_dietary_raw: list[str] = []
        for key in ("dietary", "dietary_flags", "dietaries"):
            val = meta.get(key)
            if isinstance(val, list):
                restaurant_dietary_raw.extend(val)
            elif isinstance(val, str):
                restaurant_dietary_raw.append(val)

        # Also check cuisine_types for common heuristics
        for cuisine in (restaurant.cuisine_types or []):
            c = cuisine.lower()
            if "vegan" in c:
                restaurant_dietary_raw.append("vegan")
            if "vegetarian" in c or "vegetarian" in c:
                restaurant_dietary_raw.append("vegetarian")

        restaurant_dietary = {d.lower() for d in restaurant_dietary_raw}
        overlap = user_dietary & restaurant_dietary

        if not overlap:
            return 0, None

        pts = min(15, len(overlap) * 5)
        first_flag = next(iter(overlap))
        tag = FitTag(
            label=f"{first_flag.title()}-friendly",
            type="dietary",
        )
        return pts, tag

    def _score_allergy(
        self,
        restaurant: RestaurantResult,
    ) -> tuple[int, FitTag | None]:
        """Up to 10 pts based on allergy_safe flag and warning severities."""
        if restaurant.allergy_safe and not restaurant.allergy_warnings:
            tag = FitTag(
                label="Safe for your allergy profile",
                type="allergy_safe",
            )
            return 10, tag

        # Check if only intolerance-level warnings
        if restaurant.allergy_warnings:
            severities = {w.severity for w in restaurant.allergy_warnings}
            dangerous = severities - {"intolerance"}
            if not dangerous:
                # Only intolerance warnings — partial credit
                return 5, None
            # Severe or anaphylactic warnings — no credit
            return 0, None

        # allergy_safe=False but no warnings (edge case)
        return 0, None
