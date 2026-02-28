"""
Hybrid search service — combines SQL filtering with pgvector cosine similarity.
Uses named columns only (no SELECT *).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.restaurant import RestaurantResult, RadarScores
from app.services.embedding import embed_single

logger = logging.getLogger(__name__)


async def hybrid_search(
    db: AsyncSession,
    sql_filters: dict[str, Any],
    vector_query: str,
    limit: int = 15,
) -> list[RestaurantResult]:
    """
    Execute a hybrid search over the restaurants table.

    1. Apply SQL filters (price_tier, cuisine_types, area, min_rating,
       exclude_allergens for anaphylactic allergens only).
    2. Retrieve a vector embedding for vector_query.
    3. Order by cosine distance to the embedding, fallback to rating if no embedding.
    4. Return up to `limit` results as RestaurantResult objects.
    """
    # Build embedding for semantic ranking
    query_embedding: Optional[list[float]] = await embed_single(vector_query)

    # Build dynamic WHERE clauses
    conditions: list[str] = ["r.is_active = TRUE"]
    params: dict[str, Any] = {"limit": limit}

    price_tiers: list[str] = sql_filters.get("price_tiers", [])
    if price_tiers:
        conditions.append("r.price_tier = ANY(:price_tiers)")
        params["price_tiers"] = price_tiers

    cuisine_types: list[str] = sql_filters.get("cuisine_types", [])
    if cuisine_types:
        conditions.append("r.cuisine_types && :cuisine_types")
        params["cuisine_types"] = cuisine_types

    area: Optional[str] = sql_filters.get("area")
    if area:
        conditions.append("r.area ILIKE :area")
        params["area"] = f"%{area}%"

    min_rating: Optional[float] = sql_filters.get("min_rating")
    if min_rating is not None:
        conditions.append("r.rating >= :min_rating")
        params["min_rating"] = min_rating

    # Hard filter: exclude anaphylactic allergens
    exclude_allergens: list[str] = sql_filters.get("exclude_allergens", [])
    if exclude_allergens:
        conditions.append("NOT (r.known_allergens && :exclude_allergens)")
        params["exclude_allergens"] = exclude_allergens

    where_clause = " AND ".join(conditions)

    # Choose ORDER BY based on embedding availability
    if query_embedding:
        order_clause = "rv.embedding <=> :embedding ASC, r.rating DESC NULLS LAST"
        params["embedding"] = str(query_embedding)
        join_clause = """
            LEFT JOIN (
                SELECT restaurant_id, embedding
                FROM reviews
                WHERE embedding IS NOT NULL
                ORDER BY id DESC
            ) rv ON rv.restaurant_id = r.id
        """
    else:
        order_clause = "r.rating DESC NULLS LAST"
        join_clause = ""

    sql = text(f"""
        SELECT DISTINCT ON (r.id)
            r.id,
            r.name,
            r.url,
            r.address,
            r.area,
            r.city,
            r.cuisine_types,
            r.price_tier,
            r.cost_for_two,
            r.rating,
            r.votes,
            r.lat,
            r.lng,
            r.known_allergens,
            r.allergen_confidence,
            r.meta
        FROM restaurants r
        {join_clause}
        WHERE {where_clause}
        ORDER BY r.id, {order_clause}
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    restaurants: list[RestaurantResult] = []
    for row in rows:
        meta = row.meta or {}
        restaurants.append(
            RestaurantResult(
                id=row.id,
                name=row.name,
                url=row.url,
                address=row.address,
                area=row.area,
                price_tier=row.price_tier,
                rating=float(row.rating) if row.rating else None,
                votes=row.votes or 0,
                cuisine_types=row.cuisine_types or [],
                lat=row.lat,
                lng=row.lng,
                known_allergens=row.known_allergens or [],
                allergen_confidence=row.allergen_confidence or "low",
                meta=meta,
            )
        )

    return restaurants
