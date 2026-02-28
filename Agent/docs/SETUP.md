# Agent Setup Guide — Kairos · Beyond Stars

This document covers the Agent-specific setup process: all Python dependencies from `requirements.txt`, the ingestion scripts explained in detail, and the complete environment variable reference for the Agent service.

---

## 📋 Table of Contents

1. [Agent Dependencies](#1-agent-dependencies)
2. [Environment Variables](#2-environment-variables)
3. [Scripts Reference](#3-scripts-reference)
   - [create_tables.py](#31-create_tablespy)
   - [ingest.py](#32-ingestpy)
4. [run_ingest.sh Walkthrough](#4-run_ingestsh-walkthrough)
5. [Development Workflow](#5-development-workflow)
6. [Related Documents](#related-documents)

---

## 1. Agent Dependencies

All Agent dependencies are declared in `Agent/requirements.txt`. The table below documents what each package does in the context of this project.

| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `fastapi` | `>=0.111` | Async web framework; provides `APIRouter`, `Depends`, `StreamingResponse`, `HTTPException` |
| `uvicorn[standard]` | latest | ASGI server for development; bundled with `websockets` and `httptools` via `[standard]` |
| `gunicorn` | latest | Production process manager; used with `UvicornWorker` class in `run.sh` |
| `sqlalchemy[asyncio]` | `>=2.0` | Async ORM; `create_async_engine`, `AsyncSession`, `async_sessionmaker`, `select()` query API |
| `asyncpg` | latest | Async PostgreSQL driver; required by SQLAlchemy for `postgresql+asyncpg://` connection strings |
| `pgvector` | `>=0.3` | SQLAlchemy column type `Vector(n)` and psycopg adapter for pgvector queries |
| `google-generativeai` | `>=0.5` | Google AI SDK; `genai.GenerativeModel`, `genai.embed_content()` |
| `pydantic` | `>=2.0` | Request/response schema validation; `BaseModel`, `Field`, `model_validator` |
| `pydantic-settings` | `>=2.0` | Environment variable binding; `BaseSettings`, `SettingsConfigDict` |
| `tenacity` | latest | Retry logic for LLM and embedding calls; `@retry(stop=stop_after_attempt(2))` |
| `chromadb` | latest | ChromaDB vector store client (alternative to pgvector; used in `chroma_client.py`) |
| `cachetools` | latest | `TTLCache` for the 24-hour recommendation cache in `recommendation_service.py` |
| `python-dotenv` | latest | `.env` file loading; used by `run.sh` via `export $(... xargs)` |

### Installing Dependencies

Dependencies are installed automatically by `run.sh`. To install manually:

```bash
cd Agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Adding a New Dependency

```bash
cd Agent
source .venv/bin/activate
pip install new-package
pip freeze | grep new-package >> requirements.txt
```

> ⚠️ **Warning:** Do not run `pip freeze > requirements.txt` — this overwrites the file with every installed package including transitive dependencies, which bloats the requirements file. Use `grep` to append only the package you added.

---

## 2. Environment Variables

The Agent reads configuration exclusively from environment variables, loaded from `Agent/.env` by `run.sh` and `run_ingest.sh`. The `Settings` class in `app/config.py` validates and types all values at startup.

| Variable | Type | Required | Default | Used In |
|----------|------|----------|---------|---------|
| `DATABASE_URL` | `str` | ✅ | — | `database.py` — `create_async_engine()` |
| `GOOGLE_API_KEY` | `str` | ✅ | — | `gemma.py` — `genai.configure()`, `embedding.py` |
| `SERVICE_TOKEN` | `str` | ✅ | — | `routers/users.py` — `verify_service_token()` |
| `GEMMA_MODEL` | `str` | ❌ | `gemma-2-9b-it` | `gemma.py` — model ID |
| `EMBEDDING_MODEL` | `str` | ❌ | `text-embedding-004` | `embedding.py` — model ID |
| `EMBEDDING_DIMENSIONS` | `int` | ❌ | `768` | `models/review.py` — `Vector(EMBEDDING_DIMENSIONS)` |
| `APP_ENV` | `str` | ❌ | `development` | `run.sh` — selects Uvicorn vs Gunicorn |
| `LOG_LEVEL` | `str` | ❌ | `INFO` | `main.py` — `logging.basicConfig(level=LOG_LEVEL)` |
| `ALLOWED_ORIGINS` | `list[str]` | ❌ | `["https://kairos.gokulp.online", "http://localhost:3000"]` | `main.py` — CORS middleware |

### How `run.sh` Loads Variables

```bash
# This line in run.sh exports all non-comment, non-empty .env lines:
export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)
```

This means variables set in `.env` are available as standard OS environment variables for the duration of the `run.sh` process. SQLAlchemy's `pydantic-settings` reads them via `os.environ`.

---

## 3. Scripts Reference

### 3.1 `create_tables.py`

Creates all database tables defined in the SQLAlchemy models. Safe to run multiple times (idempotent due to `CREATE TABLE IF NOT EXISTS` semantics of `Base.metadata.create_all(checkfirst=True)`).

**When to run:** On first setup of a fresh database, or after adding a new ORM model during development.

```bash
cd Agent
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python scripts/create_tables.py
```

**What it does internally:**

```python
async def main():
    await init_pgvector()          # CREATE EXTENSION IF NOT EXISTS vector
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # CREATE TABLE IF NOT EXISTS ...
    await engine.dispose()         # Close all pool connections cleanly
```

**Expected output:**

```
INFO: Creating pgvector extension...
INFO: Creating tables...
INFO: Tables created successfully.
```

### 3.2 `ingest.py`

The primary data ingestion script. Reads a Zomato Bangalore restaurants CSV, classifies allergens, generates semantic embeddings for review text, and upserts everything into PostgreSQL.

**Pipeline stages in detail:**

#### Stage 1: CSV Parsing

Each row is read with `csv.DictReader`. Key parsing functions:

- `_parse_cost(cost_str: str) -> int | None`: Handles values like `"₹500 for two"`, `"1,200"`. Strips currency symbols, removes commas, converts to integer.
- `_cost_to_tier(cost: int | None) -> str`: Maps integer cost to price tier:
  - `≤400` → `$`
  - `401–800` → `$$`
  - `801–1500` → `$$$`
  - `>1500` → `$$$$`
- `_parse_rating(rating_str: str) -> float | None`: Converts `"4.2"` to float. Returns `None` for `"NEW"` or `"-"`.

#### Stage 2: Allergen Tagging

Each restaurant is tagged with likely allergens using two methods:

1. **Cuisine-based inference:** Looks up each cuisine type in `CUISINE_ALLERGEN_MAP` from `utils/allergy_data.py`. For example, Thai cuisine maps to `["peanuts", "shellfish", "soy"]`.

2. **Text scanning:** Scans the restaurant name and review text for `ALLERGEN_SYNONYMS` values. For example, if "paneer" appears, the synonym map maps it to `"dairy"`.

The result is stored in `known_allergens ARRAY(Text)` and `allergen_confidence` is set to:
- `"high"` if any `allergen_mentions` from reviews are found
- `"medium"` if only cuisine-based inference was used
- `"low"` if no allergen data is available

#### Stage 3: Database Upsert

Each restaurant is inserted using `INSERT INTO restaurants ... ON CONFLICT (id) DO UPDATE SET ...`. This makes the ingest script re-runnable without duplicating data.

#### Stage 4: Embedding Generation

Review texts are embedded in batches of 100 using `embed_texts()`. The function:
1. Splits reviews into batches of 100
2. Calls `genai.embed_content(model=EMBEDDING_MODEL, content=batch, task_type="retrieval_document")`
3. Sleeps 0.5 seconds between batches to stay within API rate limits
4. Returns `None` for any text that fails embedding (does not abort the pipeline)

Reviews with `None` embeddings are stored without a vector — they will not appear in vector-similarity search results but will still appear in SQL-only searches.

**CLI Reference:**

```bash
# Basic usage
python scripts/ingest.py --csv data/zomato.csv

# Dry run — parse and validate without DB writes
python scripts/ingest.py --csv data/zomato.csv --dry-run

# Re-generate all embeddings (re-embeds even previously-embedded reviews)
python scripts/ingest.py --csv data/zomato.csv --re-embed

# Re-run allergen tagging only (fast — no embedding API calls)
python scripts/ingest.py --csv data/zomato.csv --retag-allergens

# Multiple flags
python scripts/ingest.py --csv data/zomato.csv --retag-allergens --dry-run
```

---

## 4. `run_ingest.sh` Walkthrough

```bash
#!/usr/bin/env bash
set -e
# Exit immediately if any command returns a non-zero exit code.
# This prevents silently continuing after a failed pip install.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Resolve the absolute path of the Agent/ directory.
# 'cd "$(dirname "$0")"' navigates to the directory containing this script.
# '&& pwd' prints the absolute path.
# This allows the script to be run from any directory.

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
# Creates a .venv if one doesn't exist yet.
# Reuses an existing venv to avoid reinstalling packages on every run.

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q
# Install/upgrade all dependencies silently.
# -q flag suppresses progress bars to keep logs readable.

export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)
# Load all non-comment, non-empty lines from .env into environment variables.
# Required so the ingest script can read DATABASE_URL and GOOGLE_API_KEY.

# "$@" passes all command-line arguments through to ingest.py:
# ./run_ingest.sh --csv data/zomato.csv --dry-run
# → python scripts/ingest.py --csv data/zomato.csv --dry-run
python "$SCRIPT_DIR/scripts/ingest.py" "$@"
```

---

## 5. Development Workflow

### Starting the Agent for Development

```bash
cd Agent
./run.sh
# Agent starts at http://localhost:4021 with hot-reload
```

### Testing a Chat Request

```bash
# First, create a test user
curl -X POST http://localhost:4021/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: your-service-token" \
  -d '{"email": "test@example.com"}'

# Then send a chat request
curl -X POST http://localhost:4021/chat \
  -H "Content-Type: application/json" \
  -H "X-User-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"message": "good biryani places in Koramangala", "conversation_history": []}' \
  --no-buffer
```

### Adding a New Service

1. Create `app/services/my_service.py`
2. Add Pydantic schemas in `app/schemas/`
3. Import and call from the appropriate router
4. Register the router in `app/main.py` if adding a new router file

### Running the Test Suite

```bash
cd Agent
source .venv/bin/activate
pip install pytest pytest-asyncio httpx pytest-cov
pytest tests/ -v --cov=app
```

---

## Related Documents

- [Agent/README.md](../README.md) — Agent module entry point
- [Agent/docs/ARCHITECTURE.md](ARCHITECTURE.md) — Agent pipeline and component reference
- [Agent/docs/API.md](API.md) — Agent API interfaces
- [docs/SETUP.md](../../docs/SETUP.md) — Full project setup (all modules)
