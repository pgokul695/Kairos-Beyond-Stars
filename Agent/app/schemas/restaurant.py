"""Pydantic schemas for restaurant results and Generative UI payloads."""

from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class AllergyWarning(BaseModel):
    """
    A structured allergy warning attached to a restaurant result.
    Rendered directly in the Frontend UI.
    """

    allergen: str                      # e.g. "peanuts"
    severity: str                      # "anaphylactic"|"severe"|"moderate"|"intolerance"
    level: str                         # "danger"|"warning"|"caution"|"info"
    emoji: str                         # "🚨"|"⚠️"|"⚡"|"ℹ️"
    title: str                         # Short display title
    message: str                       # Full human-readable message
    confidence: str                    # "high"|"medium"|"low"
    confidence_note: Optional[str] = None   # Present when confidence != 'high'


class RadarScores(BaseModel):
    """Dimension scores used in radar_comparison UI type."""

    romance: float = 0.0
    noise_level: float = 0.0
    food_quality: float = 0.0
    vegan_options: float = 0.0
    value_for_money: float = 0.0


class RestaurantResult(BaseModel):
    """
    A fully annotated restaurant result included in Generative UI payloads.
    Always includes allergy_safe flag and allergy_warnings list.
    """

    id: int
    name: str
    area: Optional[str] = None
    address: Optional[str] = None
    price_tier: Optional[str] = None
    rating: Optional[float] = None
    votes: int = 0
    cuisine_types: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    known_allergens: list[str] = Field(default_factory=list)
    allergen_confidence: str = "low"
    meta: dict[str, Any] = Field(default_factory=dict)

    # Allergy annotation — always present after AllergyGuard
    allergy_safe: bool = True
    allergy_warnings: list[AllergyWarning] = Field(default_factory=list)

    # radar_comparison only
    scores: Optional[RadarScores] = None


class GenerativeUIPayload(BaseModel):
    """
    Top-level Generative UI payload returned by the Agent for every chat turn.
    The ui_type field tells the Frontend which React component to render.
    """

    ui_type: Literal[
        "restaurant_list", "radar_comparison", "map_view", "text"
    ]
    message: str
    restaurants: list[RestaurantResult] = Field(default_factory=list)
    flagged_restaurants: list[RestaurantResult] = Field(default_factory=list)
    has_allergy_warnings: bool = False

    # text ui_type only
    follow_up_questions: Optional[list[str]] = None

    # map_view only
    map_center: Optional[dict[str, float]] = None

    model_config = ConfigDict(from_attributes=True)
