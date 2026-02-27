"""
Recommendations router — personalised restaurant feed outside of chat.

Endpoints:
  GET /recommendations/{uid}                  — ranked recommendation feed
  GET /recommendations/{uid}/{restaurant_id}/expand  — lazy-loaded rich detail

Authentication: X-User-ID header (same UUID validation as /chat).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.recommendation import (
    ExpandedDetailResponse,
    RecommendationPayload,
)
from app.services.recommendation_service import get_expanded_detail, get_recommendations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


def _validate_uid(x_user_id: str) -> uuid.UUID:
    """Parse and validate X-User-ID header as UUID v4."""
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format — must be UUID v4",
            headers={"X-Error-Code": "MISSING_USER_ID"},
        )


@router.get("/{uid}", response_model=RecommendationPayload)
async def recommendations(
    uid: str,
    limit: int = Query(default=10, ge=1, le=25),
    refresh: bool = Query(default=False),
    x_user_id: str = Header(..., alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
) -> RecommendationPayload:
    """
    Return a ranked, personalised restaurant feed for the user.

    - Scored algorithmically (FitScorer) against stored preferences
    - Enriched with a one-sentence LLM-generated consolidated review per restaurant
    - AllergyGuard applied before any restaurant reaches the response
    - Results cached per user per calendar day (TTL 24 h)
    - Pass ?refresh=true to force regeneration
    """
    caller_uid = _validate_uid(x_user_id)

    # The uid in the path must match the authenticated user
    try:
        path_uid = uuid.UUID(uid)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid uid in path",
        )

    if caller_uid != path_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-User-ID does not match uid in path",
        )

    return await get_recommendations(
        uid=caller_uid,
        db=db,
        limit=limit,
        refresh=refresh,
    )


@router.get(
    "/{uid}/{restaurant_id}/expand",
    response_model=ExpandedDetailResponse,
)
async def expand_restaurant(
    uid: str,
    restaurant_id: int,
    x_user_id: str = Header(..., alias="X-User-ID"),
    db: AsyncSession = Depends(get_db),
) -> ExpandedDetailResponse:
    """
    Return the full ExpandedDetail for a single restaurant.

    Called lazily when the user taps a recommendation card.
    Always freshly generated — not cached.
    Includes: review_summary, highlights, radar_scores, crowd_profile,
    best_for, avoid_if, why_fit_paragraph, allergy_detail.
    """
    caller_uid = _validate_uid(x_user_id)

    try:
        path_uid = uuid.UUID(uid)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid uid in path",
        )

    if caller_uid != path_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-User-ID does not match uid in path",
        )

    try:
        return await get_expanded_detail(
            uid=caller_uid,
            restaurant_id=restaurant_id,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
