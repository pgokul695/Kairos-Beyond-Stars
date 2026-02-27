"""
Kairos Agent — FastAPI application entry point.
Lifespan: create DB tables → verify connectivity → warm ChromaDB.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models import Base
from app.routers import chat, health, recommendations, users

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan handler.
    1. Create all SQLite tables (idempotent — IF NOT EXISTS).
    2. Verify DB connectivity.
    3. Warm up ChromaDB collection.
    """
    logger.info("Starting Kairos Agent (env=%s)", settings.app_env)

    # Step 1: create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")

    # Step 2: connectivity check
    from app.database import check_db_connectivity
    ok = await check_db_connectivity()
    if not ok:
        logger.error("Database connectivity check FAILED at startup.")
    else:
        logger.info("Database connectivity verified.")

    # Step 3: warm ChromaDB
    from app.services.chroma_client import get_reviews_collection
    await asyncio.to_thread(get_reviews_collection)
    logger.info("ChromaDB reviews collection ready.")

    yield

    logger.info("Shutting down Kairos Agent.")
    await engine.dispose()


app = FastAPI(
    title="Kairos Agent",
    description="Restaurant intelligence, personalisation, and allergy safety for the Kairos platform.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(users.router)
app.include_router(recommendations.router)


# ── Global exception handler ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a machine-readable error for any unhandled exception."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "AGENT_UNAVAILABLE"},
    )
