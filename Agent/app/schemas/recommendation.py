"""
Pydantic schemas for the recommendation system.
All new types live here — no existing schema file is modified.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.restaurant import AllergyWarning, RadarScores, RestaurantResult


class FitTag(BaseModel):
    """A single human-readable tag explaining why a restaurant fits the user."""

    label: str
    type: Literal["cuisine", "vibe", "price", "dietary", "allergy_safe"]


class AllergySummary(BaseModel):
    """Compact allergy summary used in the collapsed recommendation card."""

    is_safe: bool
    warnings: list[AllergyWarning]


class Highlight(BaseModel):
    """A single highlight bullet inside the expanded detail panel."""

    emoji: str
    text: str


class AllergyDetail(BaseModel):
    """Full allergy detail used inside the expanded panel."""

    is_safe: bool
    confidence: str
    warnings: list[AllergyWarning]
    safe_note: Optional[str] = None


class ExpandedDetail(BaseModel):
    """
    Rich detail payload for a single restaurant, generated lazily on /expand.
    Drives the dynamic expanded card UI.
    """

    review_summary: str
    highlights: list[Highlight]          # 3–5 items
    crowd_profile: str
    best_for: list[str]                  # 2–4 occasion tags
    avoid_if: list[str]                  # 1–3 items
    radar_scores: RadarScores
    why_fit_paragraph: str
    allergy_detail: AllergyDetail


class RecommendationItem(BaseModel):
    """A single ranked recommendation, as it appears in the feed."""

    rank: int
    restaurant: RestaurantResult
    fit_score: int                        # 0–100, algorithmic
    fit_tags: list[FitTag]               # up to 4 tags
    consolidated_review: str              # ≤160 chars, LLM-generated
    allergy_summary: AllergySummary
    expanded_detail: Optional[ExpandedDetail] = None


class RecommendationPayload(BaseModel):
    """Top-level recommendations response."""

    uid: str
    generated_at: datetime
    recommendations: list[RecommendationItem]


class ExpandedDetailResponse(BaseModel):
    """Response for the /expand endpoint."""

    restaurant_id: int
    expanded_detail: ExpandedDetail


# ── Internal helper type for the pipeline ─────────────────────────────────────

class UserProfile(BaseModel):
    """Flattened user profile used by FitScorer and the recommendation pipeline."""

    preferences: dict = {}
    allergies: dict = {}
    allergy_flags: list[str] = []
    dietary_flags: list[str] = []
    vibe_tags: list[str] = []
    preferred_price_tiers: list[str] = []
    cuisine_affinity: list[str] = []
    cuisine_aversion: list[str] = []
