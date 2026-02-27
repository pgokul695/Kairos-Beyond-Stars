"""
Local ML service — optional GPU-accelerated inference components for a GTX 1650 (4 GB VRAM).

All three components are disabled by default (USE_LOCAL_* env vars default to false).
When disabled they are never imported or loaded; the system behaves identically to its
cloud-only state.  When enabled, models are lazy-loaded on first call to avoid startup
failures when CUDA is unavailable or model weights have not been downloaded yet.

──────────────────────────────────────────────────────────────────────────────────────
MIGRATION REQUIRED — reviews.embedding_local column
──────────────────────────────────────────────────────────────────────────────────────
The local embedding model (BAAI/bge-small-en-v1.5) outputs 384-dimensional vectors,
which is different from the existing 768-dimensional gemini-embedding-001 column.
A new separate column is required.  Do NOT reuse reviews.embedding Vector(768).

Run this SQL against the vectordb database once before enabling USE_LOCAL_EMBEDDINGS:

    ALTER TABLE reviews ADD COLUMN IF NOT EXISTS embedding_local vector(384);
    CREATE INDEX IF NOT EXISTS idx_reviews_embedding_local
        ON reviews USING ivfflat (embedding_local vector_cosine_ops)
        WITH (lists = 100);

The ingestion script (scripts/ingest.py) continues to populate reviews.embedding
using gemini-embedding-001 (768d).  Local embeddings are query-time only.
──────────────────────────────────────────────────────────────────────────────────────

Components
----------
A. embed_single_local(text)          — BAAI/bge-small-en-v1.5, 384d, CUDA if available
B. rerank(query, candidates, top_k)  — cross-encoder/ms-marco-MiniLM-L-6-v2
C. classify_intent(text)             — typeform/distilbert-base-uncased-mnli (zero-shot)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.restaurant import RestaurantResult

logger = logging.getLogger(__name__)

# ── Module-level lazy sentinels ───────────────────────────────────────────────
# Each model is None until first use.  A threading lock prevents concurrent
# initialisation races when multiple async tasks call the same model for the
# first time.

_embed_model = None          # SentenceTransformer — bge-small-en-v1.5
_embed_lock = asyncio.Lock() if False else None  # replaced at runtime in _get_embed_model

_reranker_model = None       # CrossEncoder — ms-marco-MiniLM-L-6-v2
_reranker_lock_obj = None    # asyncio.Lock — created lazily to avoid import-time event-loop errors

_classifier_pipeline = None  # HuggingFace pipeline — zero-shot classification
_classifier_lock_obj = None  # asyncio.Lock


def _get_device() -> str:
    """Return 'cuda' if a GPU is available, else 'cpu'."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


# ── A. Local Embedding ────────────────────────────────────────────────────────

async def _get_embed_model():
    """Lazy-load BAAI/bge-small-en-v1.5. Thread-safe via asyncio.Lock."""
    global _embed_model, _embed_lock_obj  # noqa: PLW0603

    # Create the lock on first call (avoids event-loop-at-import-time issues)
    if not hasattr(_get_embed_model, "_lock"):
        _get_embed_model._lock = asyncio.Lock()

    async with _get_embed_model._lock:
        if _embed_model is None:
            device = _get_device()
            logger.info(
                "Loading local embedding model BAAI/bge-small-en-v1.5 on %s …", device
            )
            from sentence_transformers import SentenceTransformer  # type: ignore[import]

            _embed_model = await asyncio.to_thread(
                SentenceTransformer, "BAAI/bge-small-en-v1.5", device=device
            )
            logger.info("Local embedding model loaded (384d, device=%s).", device)

    return _embed_model


async def embed_single_local(text: str) -> list[float]:
    """
    Embed a single query string using BAAI/bge-small-en-v1.5 (384 dimensions).

    Used by hybrid_search when USE_LOCAL_EMBEDDINGS=true.
    NOTE: the reviews table must have the embedding_local Vector(384) column
          (see MIGRATION REQUIRED block at the top of this file).

    Returns a flat list[float] of length 384.
    """
    model = await _get_embed_model()
    embedding = await asyncio.to_thread(
        model.encode,
        text,
        normalize_embeddings=True,   # L2-normalise for cosine similarity
    )
    return embedding.tolist()


# ── B. Cross-Encoder Reranker ─────────────────────────────────────────────────

async def _get_reranker_model():
    """Lazy-load cross-encoder/ms-marco-MiniLM-L-6-v2."""
    global _reranker_model

    if not hasattr(_get_reranker_model, "_lock"):
        _get_reranker_model._lock = asyncio.Lock()

    async with _get_reranker_model._lock:
        if _reranker_model is None:
            device = _get_device()
            logger.info(
                "Loading cross-encoder reranker ms-marco-MiniLM-L-6-v2 on %s …", device
            )
            from sentence_transformers.cross_encoder import CrossEncoder  # type: ignore[import]

            _reranker_model = await asyncio.to_thread(
                CrossEncoder,
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                device=device,
            )
            logger.info("Reranker model loaded (device=%s).", device)

    return _reranker_model


async def rerank(
    query: str,
    candidates: list[RestaurantResult],
    top_k: int = 10,
) -> list[RestaurantResult]:
    """
    Score each candidate with the cross-encoder and return the top_k
    sorted by score descending.

    Passage text format: "{name} {cuisine_types} {area}"
    This gives the reranker enough semantic signal without hallucinating
    details not present in the DB record.

    Args:
        query:      The original user query string.
        candidates: Restaurants to rerank (typically the raw hybrid search output).
        top_k:      Maximum number of results to return.

    Returns:
        list[RestaurantResult] — sorted best-first, length <= top_k.
    """
    if not candidates:
        return candidates

    model = await _get_reranker_model()

    # Build passage strings
    passages: list[str] = []
    for c in candidates:
        cuisines = " ".join(c.cuisine_types) if c.cuisine_types else ""
        area = c.area or ""
        passages.append(f"{c.name} {cuisines} {area}".strip())

    pairs = [[query, passage] for passage in passages]

    scores: list[float] = await asyncio.to_thread(
        model.predict,
        pairs,
    )

    # Zip candidates with scores, sort descending
    scored = sorted(
        zip(candidates, scores),
        key=lambda t: t[1],
        reverse=True,
    )

    return [c for c, _ in scored[:top_k]]


# ── C. Intent Classifier ──────────────────────────────────────────────────────

_CLASSIFIER_LABELS = ["restaurant_search", "casual_chat", "clarification"]
_CASUAL_CHAT_CONFIDENCE_THRESHOLD = 0.85


async def _get_classifier():
    """Lazy-load typeform/distilbert-base-uncased-mnli zero-shot pipeline."""
    global _classifier_pipeline

    if not hasattr(_get_classifier, "_lock"):
        _get_classifier._lock = asyncio.Lock()

    async with _get_classifier._lock:
        if _classifier_pipeline is None:
            device_id = 0 if _get_device() == "cuda" else -1
            logger.info(
                "Loading zero-shot classifier typeform/distilbert-base-uncased-mnli "
                "(device_id=%d) …",
                device_id,
            )
            from transformers import pipeline  # type: ignore[import]

            _classifier_pipeline = await asyncio.to_thread(
                pipeline,
                "zero-shot-classification",
                model="typeform/distilbert-base-uncased-mnli",
                device=device_id,
            )
            logger.info("Intent classifier loaded.")

    return _classifier_pipeline


async def classify_intent(text: str) -> tuple[str, float]:
    """
    Classify the user's message into one of three intents using zero-shot classification.

    Labels: ["restaurant_search", "casual_chat", "clarification"]

    Returns:
        (intent_label: str, confidence: float)

    Callers should interpret a "casual_chat" result with confidence > 0.85 as a
    signal to short-circuit the ReAct loop and return a friendly conversational
    response instead of searching restaurants.
    """
    clf = await _get_classifier()
    result = await asyncio.to_thread(
        clf,
        text,
        _CLASSIFIER_LABELS,
    )
    # HuggingFace pipeline returns labels sorted by score descending
    top_label: str = result["labels"][0]
    top_score: float = float(result["scores"][0])
    logger.debug(
        "Intent classification: label=%s confidence=%.3f text=%r",
        top_label,
        top_score,
        text[:80],
    )
    return top_label, top_score


# Public re-export of the confidence threshold so orchestrator.py can use it
# without importing a magic constant.
CASUAL_CHAT_CONFIDENCE_THRESHOLD = _CASUAL_CHAT_CONFIDENCE_THRESHOLD
