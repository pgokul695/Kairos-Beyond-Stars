"""
ingest.py — Zomato Bangalore dataset ingestion script.

Downloads dataset from: https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants/data
Place the CSV at data/zomato.csv before running.

Usage:
    python scripts/ingest.py --csv data/zomato.csv              # full ingest
    python scripts/ingest.py --csv data/zomato.csv --re-embed   # regenerate embeddings
    python scripts/ingest.py --csv data/zomato.csv --dry-run    # parse, no DB writes
    python scripts/ingest.py --csv data/zomato.csv --retag-allergens  # re-run tagger only
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine, init_pgvector
from app.models import Base  # noqa: F401
from app.utils.allergy_data import (
    ALLERGEN_SYNONYMS,
    CANONICAL_ALLERGENS,
    CUISINE_ALLERGEN_MAP,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Column mapping helpers ───────────────────────────────────────────────────


def _parse_cost(val: object) -> Optional[int]:
    """Parse cost for two: strip '₹', ',', whitespace; return int or None."""
    if pd.isna(val):
        return None
    cleaned = re.sub(r"[₹,\s]", "", str(val))
    try:
        return int(cleaned)
    except ValueError:
        return None


def _cost_to_tier(cost: Optional[int]) -> Optional[str]:
    """Map cost_for_two to a price tier symbol."""
    if cost is None:
        return None
    if cost <= 300:
        return "$"
    if cost <= 600:
        return "$$"
    if cost <= 1200:
        return "$$$"
    return "$$$$"


def _parse_rating(val: object) -> Optional[float]:
    """Parse '4.1/5' → 4.1; drop '-' and non-numeric rows."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if s in ("-", "NEW", ""):
        return None
    match = re.match(r"(\d+\.?\d*)", s)
    return float(match.group(1)) if match else None


def _parse_votes(val: object) -> int:
    """Parse vote count; return 0 on failure."""
    try:
        return int(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0


def _parse_cuisines(val: object) -> list[str]:
    """Split comma-separated cuisines, lowercase, strip."""
    if pd.isna(val) or not str(val).strip():
        return []
    return [c.strip().lower() for c in str(val).split(",") if c.strip()]


def _parse_dishes(val: object) -> list[str]:
    """Split comma-separated dish names, strip."""
    if pd.isna(val) or not str(val).strip():
        return []
    return [d.strip() for d in str(val).split(",") if d.strip()]


def _parse_reviews(val: object) -> list[str]:
    """
    The reviews_list column contains a stringified Python list of 2-tuples:
    [('Rating 4/5', 'Review text...'), ...]
    Extract only the text portion (second element of each tuple).
    """
    if pd.isna(val) or not str(val).strip():
        return []
    try:
        parsed = ast.literal_eval(str(val))
        if isinstance(parsed, list):
            texts = []
            for item in parsed:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    texts.append(str(item[1]).strip())
                elif isinstance(item, str):
                    texts.append(item.strip())
            return [t for t in texts if t]
    except (ValueError, SyntaxError):
        pass
    return []


# ── Allergen tagger ──────────────────────────────────────────────────────────


def tag_restaurant_allergens(
    name: str,
    cuisines: list[str],
    dishes: list[str],
    reviews: list[str],
) -> tuple[list[str], str, dict[str, list[str]]]:
    """
    Tag a restaurant with allergen data from cuisine heuristics and text scanning.

    Returns:
        known_allergens: deduplicated canonical list
        confidence_level: 'high' | 'medium' | 'low'
        review_allergen_mentions: {review_text: [allergens found]}

    Steps:
        1. Cuisine heuristic → medium confidence
        2. Text scan (reviews + dishes) → upgrades to high confidence
        3. Set overall confidence level
    """
    # Step 1: cuisine heuristic
    cuisine_allergens: set[str] = set()
    for cuisine in cuisines:
        normalised = cuisine.lower().strip()
        for map_key, allergens in CUISINE_ALLERGEN_MAP.items():
            if map_key in normalised or normalised in map_key:
                cuisine_allergens.update(allergens)

    # Step 2: text scan
    text_found_allergens: set[str] = set()
    review_mentions: dict[str, list[str]] = {}

    # Build reverse lookup: token → canonical allergen
    lookup: dict[str, str] = {a: a for a in CANONICAL_ALLERGENS}
    lookup.update(ALLERGEN_SYNONYMS)

    def _scan_text(text_: str) -> list[str]:
        found = []
        tokens = re.findall(r"[a-z]+", text_.lower())
        for token in tokens:
            if token in lookup:
                canonical = lookup[token]
                if canonical not in found:
                    found.append(canonical)
        return found

    all_texts = dishes + reviews
    for text_ in all_texts:
        found = _scan_text(text_)
        if found:
            text_found_allergens.update(found)

    # Per-review allergen mentions
    for rev in reviews:
        found = _scan_text(rev)
        if found:
            review_mentions[rev] = found

    # Step 3: confidence
    all_allergens = cuisine_allergens | text_found_allergens
    if text_found_allergens:
        confidence = "high"
    elif cuisine_allergens:
        confidence = "medium"
    else:
        confidence = "low"

    return sorted(all_allergens), confidence, review_mentions


# ── Embedding helpers ────────────────────────────────────────────────────────


async def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Import at call time to allow --dry-run without Google API."""
    from app.services.embedding import embed_texts
    return await embed_texts(texts)


# ── DB helpers ───────────────────────────────────────────────────────────────


async def upsert_restaurant(session: AsyncSession, row_data: dict) -> Optional[int]:
    """Insert or update a restaurant by (name, area). Returns the restaurant id."""
    result = await session.execute(
        text("SELECT id FROM restaurants WHERE name = :name AND area = :area"),
        {"name": row_data["name"], "area": row_data["area"]},
    )
    existing = result.fetchone()

    if existing:
        await session.execute(
            text("""
                UPDATE restaurants
                SET url = :url, address = :address, cuisine_types = :cuisine_types,
                    price_tier = :price_tier, cost_for_two = :cost_for_two,
                    rating = :rating, votes = :votes,
                    known_allergens = :known_allergens,
                    allergen_confidence = :allergen_confidence,
                    meta = :meta, updated_at = NOW()
                WHERE name = :name AND area = :area
            """),
            row_data,
        )
        return existing.id
    else:
        result = await session.execute(
            text("""
                INSERT INTO restaurants
                    (name, url, address, area, city, cuisine_types, price_tier,
                     cost_for_two, rating, votes, known_allergens,
                     allergen_confidence, meta)
                VALUES
                    (:name, :url, :address, :area, :city, :cuisine_types, :price_tier,
                     :cost_for_two, :rating, :votes, :known_allergens,
                     :allergen_confidence, :meta)
                RETURNING id
            """),
            row_data,
        )
        return result.scalar()


async def insert_reviews(
    session: AsyncSession,
    restaurant_id: int,
    reviews: list[str],
    review_mentions: dict[str, list[str]],
    embeddings: list[Optional[list[float]]],
) -> None:
    """Insert reviews for a restaurant, attaching embeddings and allergen mentions."""
    for i, review_text in enumerate(reviews):
        embedding = embeddings[i] if i < len(embeddings) else None
        allergen_mentions = review_mentions.get(review_text, [])
        await session.execute(
            text("""
                INSERT INTO reviews (restaurant_id, review_text, embedding, allergen_mentions)
                VALUES (:restaurant_id, :review_text, :embedding, :allergen_mentions)
                ON CONFLICT DO NOTHING
            """),
            {
                "restaurant_id": restaurant_id,
                "review_text": review_text,
                "embedding": str(embedding) if embedding else None,
                "allergen_mentions": allergen_mentions,
            },
        )


# ── Main ingestion logic ─────────────────────────────────────────────────────


async def run_ingest(
    csv_path: str,
    dry_run: bool = False,
    re_embed: bool = False,
    retag_allergens: bool = False,
) -> None:
    """Full ingestion pipeline."""
    logger.info("Loading CSV: %s", csv_path)
    df = pd.read_csv(csv_path, low_memory=False)
    logger.info("Loaded %d rows.", len(df))

    # Remove exact duplicates on (name, location)
    name_col = "name"
    area_col = "location"

    if name_col not in df.columns or area_col not in df.columns:
        logger.error("Required columns not found. Expected 'name' and 'location'.")
        sys.exit(1)

    before = len(df)
    df = df.drop_duplicates(subset=[name_col, area_col])
    logger.info("After dedup on (name, location): %d rows (removed %d).", len(df), before - len(df))

    if dry_run:
        logger.info("-- DRY RUN: parsing only, no DB writes --")
        ok = error = 0
        for _, row in df.iterrows():
            try:
                cuisines = _parse_cuisines(row.get("cuisines"))
                dishes = _parse_dishes(row.get("dish_liked"))
                reviews = _parse_reviews(row.get("reviews_list"))
                allergens, confidence, _ = tag_restaurant_allergens(
                    str(row.get(name_col, "")), cuisines, dishes, reviews
                )
                ok += 1
            except Exception as exc:
                logger.warning("Parse error: %s", exc)
                error += 1
        logger.info("Dry run complete: %d ok, %d errors.", ok, error)
        return

    # Ensure DB and tables exist
    async with AsyncSessionLocal() as session:
        await init_pgvector(session)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    total = len(df)
    inserted = updated = skipped = 0

    for idx, row in df.iterrows():
        try:
            name = str(row.get(name_col, "")).strip()
            area = str(row.get(area_col, "")).strip()
            if not name:
                skipped += 1
                continue

            cuisines = _parse_cuisines(row.get("cuisines"))
            dishes = _parse_dishes(row.get("dish_liked"))
            reviews = _parse_reviews(row.get("reviews_list"))
            cost = _parse_cost(row.get("approx_cost(for two people)"))

            allergens, confidence, review_mentions = tag_restaurant_allergens(
                name, cuisines, dishes, reviews
            )

            meta = {}
            if not pd.isna(row.get("phone", float("nan"))):
                meta["phone"] = str(row.get("phone"))
            if dishes:
                meta["dish_liked"] = dishes
            if not pd.isna(row.get("rest_type", float("nan"))):
                meta["rest_type"] = str(row.get("rest_type"))
            if not pd.isna(row.get("listed_in(type)", float("nan"))):
                meta["listed_in"] = str(row.get("listed_in(type)"))

            row_data = {
                "name": name,
                "url": str(row.get("url", "")) or None,
                "address": str(row.get("address", "")).strip() or None,
                "area": area or None,
                "city": "Bangalore",
                "cuisine_types": cuisines,
                "price_tier": _cost_to_tier(cost),
                "cost_for_two": cost,
                "rating": _parse_rating(row.get("rate")),
                "votes": _parse_votes(row.get("votes")),
                "known_allergens": allergens,
                "allergen_confidence": confidence,
                "meta": json.dumps(meta),
            }

            async with AsyncSessionLocal() as session:
                # Check pre-existence for counter
                result = await session.execute(
                    text("SELECT id FROM restaurants WHERE name = :name AND area = :area"),
                    {"name": name, "area": area},
                )
                is_new = result.fetchone() is None

                if retag_allergens:
                    # Only update allergen fields
                    await session.execute(
                        text("""
                            UPDATE restaurants
                            SET known_allergens = :known_allergens,
                                allergen_confidence = :allergen_confidence,
                                updated_at = NOW()
                            WHERE name = :name AND area = :area
                        """),
                        {
                            "known_allergens": allergens,
                            "allergen_confidence": confidence,
                            "name": name,
                            "area": area,
                        },
                    )
                    await session.commit()
                    updated += 1
                    continue

                restaurant_id = await upsert_restaurant(session, row_data)
                if is_new:
                    inserted += 1
                else:
                    updated += 1

                if restaurant_id and reviews and not retag_allergens:
                    if re_embed:
                        # Delete existing reviews to regenerate
                        await session.execute(
                            text("DELETE FROM reviews WHERE restaurant_id = :id"),
                            {"id": restaurant_id},
                        )

                    # Check if reviews already exist (skip if not re-embedding)
                    if not re_embed:
                        count_result = await session.execute(
                            text("SELECT COUNT(*) FROM reviews WHERE restaurant_id = :id"),
                            {"id": restaurant_id},
                        )
                        if (count_result.scalar() or 0) > 0:
                            await session.commit()
                            continue

                    # Embed reviews in batches
                    embeddings = await embed_batch(reviews)
                    await insert_reviews(
                        session, restaurant_id, reviews, review_mentions, embeddings
                    )

                await session.commit()

            if (idx + 1) % 500 == 0:
                logger.info("Progress: %d / %d", idx + 1, total)

        except Exception as exc:
            logger.warning("Error on row %d (%s): %s", idx, row.get(name_col), exc)
            skipped += 1

    logger.info(
        "Ingestion complete. Inserted: %d, Updated: %d, Skipped: %d",
        inserted, updated, skipped,
    )
    await engine.dispose()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Ingest Zomato Bangalore CSV into the Agent database.")
    parser.add_argument("--csv", required=True, help="Path to zomato.csv")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no DB writes")
    parser.add_argument("--re-embed", action="store_true", help="Regenerate all embeddings")
    parser.add_argument("--retag-allergens", action="store_true", help="Re-run allergen tagger only")
    args = parser.parse_args()

    asyncio.run(
        run_ingest(
            csv_path=args.csv,
            dry_run=args.dry_run,
            re_embed=args.re_embed,
            retag_allergens=args.retag_allergens,
        )
    )


if __name__ == "__main__":
    main()
