"""Pydantic schemas package."""

from app.schemas.user import (
    UserCreate,
    UserRead,
    UserPreferencesPatch,
    AllergiesPatch,
    AllergyFlagsResponse,
    InteractionListResponse,
    InteractionSummary,
)
from app.schemas.chat import ChatRequest, ChatMessage
from app.schemas.restaurant import (
    AllergyWarning,
    RestaurantResult,
    GenerativeUIPayload,
)

__all__ = [
    "UserCreate", "UserRead", "UserPreferencesPatch",
    "AllergiesPatch", "AllergyFlagsResponse",
    "InteractionListResponse", "InteractionSummary",
    "ChatRequest", "ChatMessage",
    "AllergyWarning", "RestaurantResult", "GenerativeUIPayload",
]
