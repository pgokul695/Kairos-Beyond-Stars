"""Health check endpoints — used by load balancers and Backend uptime monitoring."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import check_db_connectivity
from app.services.embedding import embed_single

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — returns 200 if the process is running."""
    return {"status": "ok", "version": "1.0.0"}


@router.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe — checks DB connectivity and embedding API reachability.
    Returns 200 with {"db": "ok", "embedding_api": "ok"} when fully ready,
    or 503 with the failing component marked "error".
    """
    status: dict[str, str] = {}
    all_ok = True

    # Check database
    db_ok = await check_db_connectivity()
    status["db"] = "ok" if db_ok else "error"
    if not db_ok:
        all_ok = False

    # Check embedding API with a trivial call
    try:
        result = await embed_single("ping")
        status["embedding_api"] = "ok" if result else "error"
        if not result:
            all_ok = False
    except Exception as exc:
        logger.warning("Embedding API check failed: %s", exc)
        status["embedding_api"] = "error"
        all_ok = False

    http_status = 200 if all_ok else 503
    return JSONResponse(content=status, status_code=http_status)
