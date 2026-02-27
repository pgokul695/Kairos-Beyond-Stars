"""
Hybrid search service — combines SQL filtering with pgvector cosine similarity.
Uses named columns only (no SELECT *).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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
       When USE_LOCAL_EMBEDDINGS=true, uses BAAI/bge-small-en-v1.5 (384d) via
       local_ml.embed_single_local() and queries reviews.embedding_local.
       NOTE: requires the migration described in local_ml.py to add the
       embedding_local Vector(384) column before enabling this flag.
    3. Order by cosine distance to the embedding, fallback to rating if no embedding.
    4. Return up to `limit` results as RestaurantResult objects.
    """
    # Build embedding for semantic ranking
    query_embedding: Optional[list[float]] = None
    use_local = settings.use_local_embeddings
    if use_local:
        try:
            from app.services.local_ml import embed_single_local  # noqa: PLC0415

            query_embedding = await embed_single_local(vector_query)
        except Exception as exc:
            logger.warning(
                "Local embedding failed (falling back to Gemini): %s", exc
            )
            use_local = False

    if not use_local:
        query_embedding = await embed_single(vector_query)

    # Build dynamic WHERE clauses
    conditions: list[str] = ["r.is_active = TRUE"]
    params: dict[str, Any] = {"limit": limit}

    _TIER_MAP = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
    _VALID_TIERS = {"$", "$$", "$$$", "$$$$"}
    price_tiers_raw = sql_filters.get("price_tiers", [])
    price_tiers: list[str] = []
    for t in price_tiers_raw:
        if isinstance(t, int) and t in _TIER_MAP:
            price_tiers.append(_TIER_MAP[t])
        elif isinstance(t, str) and t in _VALID_TIERS:
            price_tiers.append(t)
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

    # Choose ORDER BY based on embedding availability and embedding source
    if query_embedding:
        if settings.use_local_embeddings:
            # Use the 384-dimension local embedding column
            # MIGRATION REQUIRED: see local_ml.py header for ALTER TABLE statement
            embedding_col = "embedding_local"
        else:
            embedding_col = "embedding"
        order_clause = f"rv.{embedding_col} <=> :embedding ASC, r.rating DESC NULLS LAST"
        params["embedding"] = str(query_embedding)
        join_clause = f"""
            LEFT JOIN (
                SELECT restaurant_id, {embedding_col}
                FROM reviews
                WHERE {embedding_col} IS NOT NULL
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
