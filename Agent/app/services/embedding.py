"""
Embedding service — wraps Google text-embedding-004.
Batches requests at 100 texts per call with a 0.5 s sleep between batches.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

# Initialise the Google AI client
genai.configure(api_key=settings.google_api_key)


async def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Return 768-dimensional embeddings for a list of texts.

    Batches at 100 texts per request with a 0.5 s sleep between batches
    to respect API rate limits. Returns None for any text that fails.
    """
    results: list[Optional[list[float]]] = [None] * len(texts)
    batch_size = 100
    sleep_between = 0.5

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        try:
            response = await asyncio.to_thread(
                genai.embed_content,
                model=f"models/{settings.embedding_model}",
                content=batch,
                task_type="retrieval_document",
            )
            embeddings = response.get("embedding", [])
            for i, emb in enumerate(embeddings):
                results[start + i] = emb
        except Exception as exc:
            logger.error(
                "Embedding batch %d–%d failed: %s",
                start,
                start + len(batch),
                exc,
            )

        if start + batch_size < len(texts):
            await asyncio.sleep(sleep_between)

    return results


async def embed_single(text: str) -> Optional[list[float]]:
    """Return a 768-dimensional embedding for a single text, or None on error."""
    try:
        response = await asyncio.to_thread(
            genai.embed_content,
            model=f"models/{settings.embedding_model}",
            content=text,
            task_type="retrieval_query",
        )
        return response.get("embedding")
    except Exception as exc:
        logger.error("Single embedding failed: %s", exc)
        return None
