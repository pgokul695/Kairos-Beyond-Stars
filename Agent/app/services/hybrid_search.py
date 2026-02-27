"""
Hybrid search service — SQLite scalar filtering + ChromaDB cosine similarity.

Flow:
  1. Query ChromaDB with a text embedding → ordered list of restaurant_ids.
  2. Fetch matching restaurants from SQLite with scalar filters.
  3. Python-side filter for array fields (cuisine_types, allergens).
  4. Rank by ChromaDB similarity order, then by rating as tiebreak.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas.restaurant import RestaurantResult, RadarScores
from app.services.embedding import embed_single
from app.services.chroma_client import get_reviews_collection

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

    # Step 1: ChromaDB vector search → ordered restaurant IDs
    chroma_ranked_ids: list[int] = []
    if query_embedding:
        def _chroma_query() -> list[int]:
            collection = get_reviews_collection()
            count = collection.count()
            if count == 0:
                return []
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(200, count),
                include=["metadatas"],
            )
            seen: set[int] = set()
            ids: list[int] = []
            for meta in (results.get("metadatas") or [[]])[0]:
                rid = meta.get("restaurant_id")
                if rid is not None:
                    rid = int(rid)
                    if rid not in seen:
                        ids.append(rid)
                        seen.add(rid)
            return ids

        chroma_ranked_ids = await asyncio.to_thread(_chroma_query)

    # Step 2: SQLite query with scalar filters
    conditions: list[str] = ["r.is_active = 1"]
    params: dict[str, Any] = {}

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
        placeholders = ", ".join(f":pt{i}" for i in range(len(price_tiers)))
        conditions.append(f"r.price_tier IN ({placeholders})")
        for i, pt in enumerate(price_tiers):
            params[f"pt{i}"] = pt

    area: Optional[str] = sql_filters.get("area")
    if area:
        conditions.append("r.area LIKE :area")
        params["area"] = f"%{area}%"

    min_rating: Optional[float] = sql_filters.get("min_rating")
    if min_rating is not None:
        conditions.append("r.rating >= :min_rating")
        params["min_rating"] = min_rating

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
        SELECT
            r.id, r.name, r.url, r.address, r.area,
            r.cuisine_types, r.price_tier, r.cost_for_two,
            r.rating, r.votes, r.lat, r.lng,
            r.known_allergens, r.allergen_confidence, r.meta
        FROM restaurants r
        WHERE {where_clause}
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    # Step 3: Python-side array filters
    cuisine_types: list[str] = sql_filters.get("cuisine_types", [])
    exclude_allergens: list[str] = sql_filters.get("exclude_allergens", [])

    def _parse_json_field(val: Any) -> list:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return []
        return []

    filtered: list[tuple] = []
    for row in rows:
        cuisines = _parse_json_field(row.cuisine_types)
        allergens = _parse_json_field(row.known_allergens)

        if cuisine_types and not any(c in cuisines for c in cuisine_types):
            continue
        if exclude_allergens and any(a in allergens for a in exclude_allergens):
            continue

        filtered.append((row, cuisines, allergens))

    # Step 4: rank by ChromaDB order, then descending rating
    chroma_index = {rid: i for i, rid in enumerate(chroma_ranked_ids)}
    filtered.sort(
        key=lambda t: (
            chroma_index.get(t[0].id, len(chroma_ranked_ids)),
            -(float(t[0].rating) if t[0].rating else 0.0),
        )
    )

    restaurants: list[RestaurantResult] = []
    for row, cuisines, allergens in filtered[:limit]:
        meta = _parse_json_field(row.meta) if isinstance(row.meta, str) else (row.meta or {})
        if isinstance(meta, list):
            meta = {}
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
                cuisine_types=cuisines,
                lat=row.lat,
                lng=row.lng,
                known_allergens=allergens,
                allergen_confidence=row.allergen_confidence or "low",
                meta=meta,
            )
        )

    return restaurants
