"""Pydantic schemas for user management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    """Body for POST /users/{uid} — sent by Backend after user registration."""

    preferences: dict[str, Any] = Field(default_factory=dict)
    allergies: dict[str, Any] = Field(default_factory=dict)
    dietary_flags: list[str] = Field(default_factory=list)
    vibe_tags: list[str] = Field(default_factory=list)
    allergy_flags: list[str] = Field(default_factory=list)
    preferred_price_tiers: list[str] = Field(default_factory=list)


class UserRead(BaseModel):
    """Full user profile returned by GET /users/{uid}."""

    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    preferences: dict[str, Any]
    allergies: dict[str, Any]
    allergy_flags: list[str]
    dietary_flags: list[str]
    vibe_tags: list[str]
    preferred_price_tiers: list[str]
    interaction_count: int
    last_active_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class UserPreferencesPatch(BaseModel):
    """Body for PATCH /users/{uid} — deep-merges into preferences only."""

    preferences: dict[str, Any] = Field(default_factory=dict)


class AllergiesPatch(BaseModel):
    """
    Body for PATCH /users/{uid}/allergies.
    This is a FULL REPLACE of the allergies object — not a merge.
    Prevents stale allergy data accumulating over time.
    """

    confirmed: list[str] = Field(default_factory=list)
    intolerances: list[str] = Field(default_factory=list)
    severity: dict[str, str] = Field(default_factory=dict)
    # severity values: "anaphylactic" | "severe" | "moderate" | "intolerance"


class AllergyFlagsResponse(BaseModel):
    """Response for PATCH /users/{uid}/allergies."""

    uid: uuid.UUID
    allergy_flags: list[str]
    updated: bool


class InteractionSummary(BaseModel):
    """Serialised record of a single chat interaction."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: uuid.UUID
    user_query: str
    agent_response: dict[str, Any]
    ui_type: Optional[str]
    restaurant_ids: Optional[list[int]]
    allergy_warnings_shown: bool
    allergens_flagged: list[str]
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    created_at: datetime


class InteractionListResponse(BaseModel):
    """Paginated list of interactions for GET /users/{uid}/interactions."""

    interactions: list[InteractionSummary]
    total: int
    limit: int
    offset: int
