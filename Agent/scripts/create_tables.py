"""
create_tables.py — idempotent table creation script.
Run this before starting the Agent for the first time, or after schema changes.
Safe to run multiple times (all DDL uses IF NOT EXISTS).

Usage:
    python scripts/create_tables.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal, engine, init_pgvector
from app.models import Base  # noqa: F401 — triggers model registration


async def main() -> None:
    """Create pgvector extension and all tables."""
    print("Creating pgvector extension...")
    async with AsyncSessionLocal() as session:
        await init_pgvector(session)
    print("  ✓ pgvector extension ready")

    print("Creating tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓ All tables created (IF NOT EXISTS)")

    print("\nDone. Run `python scripts/ingest.py --csv data/zomato.csv` next.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
