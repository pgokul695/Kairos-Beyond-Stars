# Kairos Agent — Complete Architecture Overview

> Last updated by automated review. Reflects production codebase state.

---

## Table of Contents

1. [Platform Context](#1-platform-context)
2. [Directory Structure](#2-directory-structure)
3. [API Surface](#3-api-surface)
4. [Request Lifecycle — POST /chat](#4-request-lifecycle--post-chat)
5. [The 5-Step Orchestrator Loop](#5-the-5-step-orchestrator-loop)
6. [LLM Chain — Primary & Fallback](#6-llm-chain--primary--fallback)
7. [Embedding Pipeline](#7-embedding-pipeline)
8. [Hybrid Search](#8-hybrid-search)
9. [AllergyGuard — Safety Layer](#9-allergyguard--safety-layer)
10. [Generative UI Payload](#10-generative-ui-payload)
11. [Data Model](#11-data-model)
12. [Authentication Model](#12-authentication-model)
13. [Background Tasks](#13-background-tasks)
14. [Startup Sequence](#14-startup-sequence)
15. [Configuration Reference](#15-configuration-reference)
16. [Prompt Templates](#16-prompt-templates)
17. [Data Ingestion Pipeline](#17-data-ingestion-pipeline)

---

## 1. Platform Context

The Kairos platform has four independent modules:

```
┌─────────────────────────────────────────────────────────────┐
│                     Kairos Platform                         │
│                                                             │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────┐  │
│   │ Frontend │   │ Backend  │   │  Agent   │   │  Mail │  │
│   │ (Next.js)│   │ (Django) │   │(FastAPI) │   │       │  │
│   └────┬─────┘   └────┬─────┘   └────┬─────┘   └───────┘  │
│        │              │              │                      │
│        │  X-User-ID   │  X-Service-  │                      │
│        │  (UID from   │  Token       │                      │
│        │   Backend)   │              │                      │
│        └──────────────┼──────────────┘                      │
│                       │                                     │
│                  PostgreSQL                                  │
│              (localhost:5433/vectordb)                       │
└─────────────────────────────────────────────────────────────┘
```

- **Frontend** calls `POST /chat` passing `X-User-ID: <uid>` (received from Backend at login)
- **Backend** calls `POST /users/{uid}`, `PATCH /users/{uid}/allergies`, `DELETE /users/{uid}/*` passing `X-Service-Token`
- The Agent maintains its own PostgreSQL database (users, restaurants, reviews, interactions)

---

## 2. Directory Structure

```
Agent/
├── app/
│   ├── main.py                 # FastAPI app, lifespan, CORS, router registration
│   ├── config.py               # Pydantic Settings — all env var bindings
│   ├── database.py             # AsyncEngine, AsyncSessionLocal, Base, get_db
│   │
│   ├── models/
│   │   ├── user.py             # User ORM (uid, preferences, allergies, flags)
│   │   ├── restaurant.py       # Restaurant ORM (cuisine_types, allergens, meta)
│   │   ├── review.py           # Review ORM (text, embedding Vector(768))
│   │   └── interaction.py      # Interaction ORM (query, response, restaurant_ids)
│   │
│   ├── schemas/
│   │   ├── chat.py             # ChatRequest (message, conversation_history)
│   │   ├── restaurant.py       # AllergyWarning, RadarScores, RestaurantResult,
│   │   │                       #   GenerativeUIPayload
│   │   └── user.py             # UserCreate, UserUpdate, AllergyUpdate, UserOut
│   │
│   ├── routers/
│   │   ├── chat.py             # POST /chat — SSE stream, X-User-ID auth
│   │   ├── health.py           # GET /health, GET /ready
│   │   └── users.py            # CRUD /users/{uid}, X-Service-Token auth
│   │
│   ├── services/
│   │   ├── orchestrator.py     # 5-step loop — the core Agent brain
│   │   ├── gemma.py            # LLM wrapper — primary + fallback model chain
│   │   ├── embedding.py        # Embedding client (gemini-embedding-001, 768d)
│   │   ├── hybrid_search.py    # SQL + pgvector cosine similarity search
│   │   ├── allergy_guard.py    # Safety layer — annotate + sort + flag restaurants
│   │   └── profiler.py         # Background preference extractor (never touches allergies)
│   │
│   └── utils/
│       ├── prompts.py          # All LLM prompt builders (decomp, eval, profiler, context)
│       └── allergy_data.py     # CANONICAL_ALLERGENS, ALLERGEN_SYNONYMS, CUISINE_ALLERGEN_MAP
│
├── scripts/
│   └── ingest.py               # Zomato CSV → PostgreSQL + embedding ingestion
│
├── data/                       # Zomato Bangalore dataset CSV
├── docs/
│   └── ARCHITECTURE.md         # This file
│
├── .env                        # Runtime secrets (not committed)
├── .env.example                # Template for .env
├── requirements.txt            # Python dependencies
├── run.sh                      # Production start script (port 4021)
├── run_ingest.sh               # One-time ingestion helper
└── docker-compose.yml          # PostgreSQL + pgvector container
```

---

## 3. API Surface

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | None | Liveness check — always 200 |
| `GET`  | `/ready` | None | Readiness check — DB + embedding API |
| `POST` | `/chat` | `X-User-ID` | Streaming SSE chat endpoint |
| `POST` | `/users/{uid}` | `X-Service-Token` | Create user profile |
| `GET`  | `/users/{uid}` | `X-Service-Token` | Get user profile |
| `PATCH`| `/users/{uid}` | `X-Service-Token` | Update user preferences |
| `PATCH`| `/users/{uid}/allergies` | `X-Service-Token` | Update allergy profile |
| `DELETE`| `/users/{uid}` | `X-Service-Token` | Delete user + cascade |
| `DELETE`| `/users/{uid}/allergies` | `X-Service-Token` | Clear allergy data |

### Headers

| Header | Used by | Purpose |
|--------|---------|---------|
| `X-User-ID` | Frontend | UUID v4 — identifies the authenticated user |
| `X-Service-Token` | Backend | Shared secret (`KairosTest`) for server-to-server calls |

---

## 4. Request Lifecycle — POST /chat

```
Frontend
  │
  │  POST /chat
  │  X-User-ID: <uuid>
  │  { "message": "...", "conversation_history": [...] }
  │
  ▼
app/routers/chat.py
  │  Validate UUID format
  │  Return StreamingResponse(orchestrate(...), media_type="text/event-stream")
  │
  ▼
app/services/orchestrator.py  ──  orchestrate(uid, message, history, db)
  │
  │  [STREAMING SSE]
  │
  ├─► {"event":"thinking","data":{"step":"fetching_context"}}
  │
  │  Step 1: fetch user context from DB
  │          (preferences, allergies, allergy_flags, dietary_flags, vibe_tags)
  │
  ├─► {"event":"thinking","data":{"step":"decomposing"}}
  │
  │  Step 2: Gemma call #1 — decompose query into structured filters
  │
  ├─► {"event":"thinking","data":{"step":"searching","filters":{...}}}
  │
  │  Step 3: hybrid_search(db, sql_filters, vector_query, limit=15)
  │
  ├─► {"event":"thinking","data":{"step":"evaluating","count":N}}
  │
  │  Step 4: Gemma call #2 — score top 10 restaurants on 5 dimensions
  │
  ├─► {"event":"thinking","data":{"step":"checking_allergies"}}
  │
  │  Step 5: AllergyGuard.check(top_5_restaurants, user_allergies)
  │
  └─► {"event":"result","data": <GenerativeUIPayload> }

  [After stream closes]
  asyncio.create_task(_save_interaction(...))
  asyncio.create_task(_run_profiler(...))
```

---

## 5. The 5-Step Orchestrator Loop

Located in `app/services/orchestrator.py`. The function `orchestrate()` is an `async generator` that yields SSE-formatted strings.

### Step 1 — Context Retrieval

Fetches from `users` table:
- `preferences` (JSONB) → `build_user_context()` → human-readable string for prompts
- `allergies` (JSONB) → `build_allergy_context()` → safety-critical string for prompts
- `allergy_flags` (TEXT[]) — for GIN-indexed fast queries
- `dietary_flags` (TEXT[]) — e.g. `["vegan", "halal"]`
- `vibe_tags` (TEXT[]) — e.g. `["quiet", "romantic"]`
- Last 5 interactions for conversation history context

### Step 2 — Query Decomposition (Gemma #1)

Calls `call_gemma_json(decomposition_prompt)`.

**Input prompt includes:**
- User context string
- Allergy context string (SAFETY-CRITICAL section)
- Last 3 conversation turns
- Current message

**Output JSON schema:**
```json
{
  "intent": "find_restaurant",
  "sql_filters": {
    "price_tiers": ["$$", "$$$"],
    "cuisine_types": ["south indian"],
    "area": "Koramangala",
    "min_rating": 4.0,
    "exclude_allergens": ["peanuts"]
  },
  "vector_query": "quiet romantic anniversary dinner",
  "ui_preference": "radar_comparison",
  "needs_clarification": false,
  "clarification_question": null
}
```

**Anaphylactic override:** After decomposition, the orchestrator explicitly adds all `anaphylactic`-severity allergens to `sql_filters.exclude_allergens` — this cannot be forgotten by the LLM.

**Clarification short-circuit:** If `needs_clarification: true`, returns a `text` UI payload immediately without searching.

### Step 3 — Hybrid Search

Calls `hybrid_search(db, sql_filters, vector_query, limit=15)`.

Returns up to 15 `RestaurantResult` candidates. See [Hybrid Search](#8-hybrid-search) section.

**Empty result short-circuit:** If no candidates found, returns a `text` payload immediately.

### Step 4 — Evaluation & Scoring (Gemma #2)

Takes top 10 candidates from Step 3.

Calls `call_gemma_json(evaluation_prompt)`.

**Scoring dimensions (0–10 each):**
- `romance` — intimacy / ambiance
- `noise_level` — quietness (10 = silent)
- `food_quality` — food variety and quality
- `vegan_options` — plant-based availability
- `value_for_money` — price vs quality ratio

**Composite score** = `(romance + food_quality + value_for_money + vegan_options) / 4`

Results are sorted by composite score descending; top 5 proceed to Step 5.

**Graceful degradation:** If Gemma fails, `scores_list = []` — all scores default to 0. Process continues without crashing.

### Step 5 — AllergyGuard

Calls `_allergy_guard.check(top_5_results, user_allergies)`.

The `_allergy_guard` is a module-level singleton `AllergyGuard()` — instantiated once at import time, never per-request.

See [AllergyGuard](#9-allergyguard--safety-layer) section.

### Step 6 — Response Construction

Builds the `GenerativeUIPayload` with:
- `ui_type` from decomposition (`restaurant_list` | `radar_comparison` | `map_view` | `text`)
- Natural language `message` (e.g. "I found 4 restaurants for you! 1 has a high-risk allergy note...")
- `restaurants` = `allergy_result.safe_restaurants`
- `flagged_restaurants` = `allergy_result.flagged_restaurants`
- `has_allergy_warnings`

---

## 6. LLM Chain — Primary & Fallback

Located in `app/services/gemma.py`.

```
call_gemma(prompt)
  │
  ├─ _call_model(_primary_model, prompt, timeout=30s)
  │     Model: gemini-2.5-flash
  │     │
  │     ├─ SUCCESS → return text
  │     │
  │     └─ ANY EXCEPTION (quota, timeout, network, 404)
  │           │
  │           └─ log warning with error type
  │
  ├─ _call_model(_fallback_model, prompt, timeout=60s)
  │     Model: gemma-3-12b-it
  │     │
  │     ├─ SUCCESS → log info + return text
  │     │
  │     └─ EXCEPTION → raise GemmaError(both models failed)
  │
call_gemma_json(prompt)
  │
  ├─ call_gemma(prompt) → raw text
  ├─ _strip_fences(raw)  — removes ```json ... ``` markdown
  └─ json.loads(cleaned) → Any  (raises GemmaError on parse fail)
```

### Timeout rationale

| Model | Timeout | Reason |
|-------|---------|--------|
| `gemini-2.5-flash` | 30 s | Fast hosted model — 30s is generous |
| `gemma-3-12b-it` | 60 s | Larger model, slower inference, needs extra headroom |

### Quota detection

`_is_quota_error(exc)` checks for any of: `RESOURCE_EXHAUSTED`, `429`, `quota`, `rate limit` in the exception string. Triggers a more specific log message but does NOT change fallback behaviour — all exceptions fall through to fallback.

---

## 7. Embedding Pipeline

Located in `app/services/embedding.py`.

**Model:** `gemini-embedding-001`  
**Dimensions:** 768 (via Matryoshka truncation — `output_dimensionality=768`)

```python
embed_texts(texts: list[str]) -> list[list[float]]
embed_single(text: str) -> list[float]
```

Both functions pass `output_dimensionality=settings.embedding_dimensions` to the API.

**Used in two contexts:**
1. **Ingestion** (`scripts/ingest.py`): embed review texts → store in `reviews.embedding` column as `Vector(768)`
2. **Query time** (`hybrid_search.py`): embed `vector_query` string → use for cosine similarity ordering

**`/ready` health check** calls `embed_single("ping")` to verify the embedding API is live.

---

## 8. Hybrid Search

Located in `app/services/hybrid_search.py`.

```
hybrid_search(db, sql_filters, vector_query, limit=15)
  │
  ├─ embed_single(vector_query) → query_embedding: list[float]
  │
  ├─ Build dynamic WHERE clause from sql_filters:
  │     price_tiers      → r.price_tier = ANY(:price_tiers)
  │     cuisine_types    → r.cuisine_types && :cuisine_types
  │     area             → r.area ILIKE :area
  │     min_rating       → r.rating >= :min_rating
  │     exclude_allergens → NOT (r.known_allergens && :exclude_allergens)  ← HARD FILTER
  │
  ├─ JOIN reviews table (latest review with embedding per restaurant)
  │
  ├─ ORDER BY:
  │     With embedding:    rv.embedding <=> :embedding ASC, r.rating DESC
  │     Without embedding: r.rating DESC
  │
  ├─ DISTINCT ON (r.id) to deduplicate
  │
  └─ Return list[RestaurantResult] (up to limit=15)
```

**Key design decisions:**
- `exclude_allergens` is a **hard SQL filter** — anaphylactic allergens are excluded at database level, not just annotated
- `DISTINCT ON (r.id)` prevents duplicate restaurants from multiple review matches
- Falls back gracefully to rating-only sort if embedding is unavailable

---

## 9. AllergyGuard — Safety Layer

Located in `app/services/allergy_guard.py`.

AllergyGuard is the final safety check before any restaurant reaches the user. It runs on **every** request and **cannot be bypassed**.

### Core rules

1. **Never silently hide** a restaurant — always show it with a clear warning
2. **Exception:** `severity == "anaphylactic"` AND `allergen_confidence == "high"` → move to `flagged_restaurants` (danger banner)
3. **Sort order:** `allergy_safe=True` first, then by worst-case severity (`intolerance` → `moderate` → `severe` → `anaphylactic` last)
4. **Warning language** must match severity — no false alarms for intolerances, no soft-pedalling for anaphylactic risks
5. **Confidence note** added when `allergen_confidence != "high"`

### Warning severity mapping

| Severity | Level | Emoji | Title |
|----------|-------|-------|-------|
| `anaphylactic` | `danger` | 🚨 | Anaphylaxis Risk |
| `severe` | `warning` | ⚠️ | Allergy Warning |
| `moderate` | `caution` | ⚡ | May Contain |
| `intolerance` | `info` | ℹ️ | Contains |

### Input/Output

```
AllergyGuard.check(restaurants, user_allergies)
  │
  │  user_allergies = {
  │    "confirmed": ["peanuts", "dairy"],
  │    "intolerances": ["gluten"],
  │    "severity": {"peanuts": "anaphylactic", "dairy": "severe"}
  │  }
  │
  └─► AllergyCheckResult {
        safe_restaurants:     list[RestaurantResult]  # annotated, sorted safest-first
        flagged_restaurants:  list[RestaurantResult]  # anaphylactic + high confidence
        has_any_warnings:     bool
      }
```

### Allergen data source

`app/utils/allergy_data.py`:
- **14 canonical EU allergens** + common extras
- **`ALLERGEN_SYNONYMS`**: `"paneer"` → `"dairy"`, `"maida"` → `"gluten"`, `"til"` → `"sesame"`, etc.
- **`CUISINE_ALLERGEN_MAP`**: heuristic allergen inference per cuisine type (used at ingestion for medium-confidence annotation)
- **`CONFIDENCE_NOTE`**: templated notes appended when confidence is not `"high"`

---

## 10. Generative UI Payload

The `GenerativeUIPayload` (in `app/schemas/restaurant.py`) is the top-level response for every chat turn. The `ui_type` field tells the Frontend which React component to render.

```python
class GenerativeUIPayload(BaseModel):
    ui_type: Literal["restaurant_list", "radar_comparison", "map_view", "text"]
    message: str                              # Natural language summary
    restaurants: list[RestaurantResult]       # Safe restaurants
    flagged_restaurants: list[RestaurantResult]  # Danger-flagged restaurants
    has_allergy_warnings: bool
    follow_up_questions: Optional[list[str]]  # text ui_type only
```

### UI Types

| `ui_type` | Frontend Component | When used |
|-----------|-------------------|-----------|
| `restaurant_list` | Card grid | Default — list of recommended restaurants |
| `radar_comparison` | Radar chart | When user wants to compare options (romance, food, noise, etc.) |
| `map_view` | Interactive map | When user asks about location / area |
| `text` | Message bubble | Clarification requests, errors, no-result messages |

### RestaurantResult fields

Each restaurant in the payload includes:
- Core fields: `id`, `name`, `area`, `address`, `price_tier`, `rating`, `votes`, `cuisine_types`, `url`, `lat`, `lng`
- Allergy fields: `known_allergens`, `allergen_confidence`, `allergy_safe`, `allergy_warnings`
- Scores (radar only): `scores: RadarScores` with `romance`, `noise_level`, `food_quality`, `vegan_options`, `value_for_money`

---

## 11. Data Model

Four tables in PostgreSQL (`vectordb`):

### `users`

| Column | Type | Description |
|--------|------|-------------|
| `uid` | UUID PK | Sourced from Backend — never generated by Agent |
| `preferences` | JSONB | Rich preference snapshot (dietary, vibes, cuisine_affinity, etc.) |
| `allergies` | JSONB | **Safety-critical** — only updated via PATCH /users/{uid}/allergies |
| `allergy_flags` | TEXT[] | Denormalised flat list for fast GIN queries |
| `dietary_flags` | TEXT[] | e.g. `["vegan", "halal"]` |
| `vibe_tags` | TEXT[] | e.g. `["quiet", "romantic"]` |
| `preferred_price_tiers` | TEXT[] | e.g. `["$$", "$$$"]` |
| `interaction_count` | INT | Incremented by profiler on every chat turn |
| `last_active_at` | TIMESTAMP | Updated on every chat turn |

### `restaurants`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT PK | Auto-increment |
| `name` | TEXT | Restaurant name |
| `cuisine_types` | TEXT[] | e.g. `["south indian", "chinese"]` |
| `price_tier` | VARCHAR | `$` / `$$` / `$$$` / `$$$$` |
| `cost_for_two` | INT | Average cost in INR |
| `rating` | NUMERIC(3,1) | Zomato rating (0.0–5.0) |
| `known_allergens` | TEXT[] | Canonical allergen names (`&&` operator used in search) |
| `allergen_confidence` | VARCHAR | `high` / `medium` / `low` |
| `lat` / `lng` | DOUBLE | For map_view UI |
| `meta` | JSONB | Flexible extra data |

### `reviews`

| Column | Type | Description |
|--------|------|-------------|
| `id` | INT PK | Auto-increment |
| `restaurant_id` | INT FK | → `restaurants.id` |
| `text` | TEXT | Review text |
| `embedding` | Vector(768) | pgvector embedding — cosine distance for semantic search |

Index: `ivfflat` on `reviews.embedding vector_cosine_ops`

### `interactions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID PK | |
| `uid` | UUID FK | → `users.uid` |
| `user_query` | TEXT | Original user message |
| `agent_response` | JSONB | Full GenerativeUIPayload |
| `ui_type` | VARCHAR | Denormalised for analytics |
| `restaurant_ids` | INT[] | IDs of all restaurants shown |
| `allergy_warnings_shown` | BOOLEAN | |
| `allergens_flagged` | TEXT[] | Allergens that triggered warnings |
| `created_at` | TIMESTAMP | |

---

## 12. Authentication Model

The Agent uses **two separate authentication schemes** — one per caller:

### Frontend → Agent: `X-User-ID`

```
Frontend (already has JWT from Backend)
  │
  │  POST /chat
  │  X-User-ID: <uid>   ← UUID extracted from JWT by Frontend
  │
  ▼
Agent validates UUID format only.
JWT verification is the Backend's responsibility — Agent trusts the header.
```

### Backend → Agent: `X-Service-Token`

```python
def verify_service_token(x_service_token: str = Header(...)):
    if x_service_token.strip() != settings.service_token.strip():
        logger.warning("Token mismatch: received len=%d, expected len=%d",
                       len(x_service_token.strip()), len(settings.service_token.strip()))
        raise HTTPException(status_code=401, detail="Invalid service token")
```

- Shared secret in `.env` as `SERVICE_TOKEN=KairosTest`
- `.strip()` on both sides guards against invisible whitespace in env files
- Used on all `/users/` endpoints

---

## 13. Background Tasks

After the SSE stream closes, two `asyncio.create_task()` fire-and-forget tasks run in the background. Each opens its own `AsyncSessionLocal()` session (the request session may be closed by the time they run).

### `_save_interaction(uid, message, payload, restaurant_ids, allergens_flagged, has_warnings)`

Inserts into `interactions` table. Never raises — any exception is logged as ERROR.

### `_run_profiler(uid, message, payload_dict)`

Calls `update_user_profile()` from `app/services/profiler.py`.

The profiler:
1. Calls `call_gemma_json(profiler_prompt)` to extract preference signals
2. Sanitises output — strips any allergy-related keys (allergies are **never** inferred from chat)
3. Deep-merges lists (union + deduplicate), replaces scalar values
4. Updates `users.preferences`, `dietary_flags`, `vibe_tags`, `interaction_count`, `last_active_at`
5. If Gemma fails OR no new preferences found: bumps `interaction_count` only

**Allowed preference keys:**
```python
_ALLOWED_PREFERENCE_KEYS = {
    "dietary", "vibes", "cuisine_affinity", "cuisine_aversion", "price_comfort"
}
```

---

## 14. Startup Sequence

Handled by the FastAPI `lifespan` context manager in `app/main.py`:

```
Application startup
  │
  ├─ 1. Register pgvector extension
  │       CREATE EXTENSION IF NOT EXISTS vector
  │
  ├─ 2. Create all tables
  │       Base.metadata.create_all(bind=engine)
  │       (users, restaurants, reviews, interactions + ivfflat index)
  │
  └─ 3. Connectivity check
          SELECT 1  — verifies DB is reachable before accepting traffic

Application shutdown
  └─ (no-op — SQLAlchemy async engine disposes automatically)
```

CORS is configured with `settings.allowed_origins_list` (comma-split from `ALLOWED_ORIGINS` env var).

---

## 15. Configuration Reference

All configuration lives in `app/config.py` as a `pydantic_settings.BaseSettings` class. Values are loaded from `.env`.

| Env var | Default | Description |
|---------|---------|-------------|
| `DATABASE_URL` | *required* | `postgresql+asyncpg://...` |
| `GOOGLE_API_KEY` | *required* | Google Generative AI API key |
| `GEMMA_MODEL` | `gemini-2.5-flash` | Primary LLM |
| `GEMMA_FALLBACK_MODEL` | `gemma-3-12b-it` | Fallback LLM (used if primary fails) |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `EMBEDDING_DIMENSIONS` | `768` | Output dimensionality (Matryoshka truncation) |
| `SERVICE_TOKEN` | *required* | Shared secret for Backend → Agent calls |
| `ALLOWED_ORIGINS` | `""` | Comma-separated CORS origins |
| `APP_ENV` | `development` | `development` / `production` |
| `LOG_LEVEL` | `INFO` | Python log level |
| `PORT` | `4021` | HTTP port (set in `run.sh`, not `config.py`) |

### Production `.env`

```dotenv
DATABASE_URL=postgresql+asyncpg://myuser:mypassword@localhost:5433/vectordb
GOOGLE_API_KEY=<key>
GEMMA_MODEL=gemini-2.5-flash
GEMMA_FALLBACK_MODEL=gemma-3-12b-it
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768
SERVICE_TOKEN=KairosTest
ALLOWED_ORIGINS=https://kairos.gokulp.online,http://localhost:3000
APP_ENV=development
LOG_LEVEL=INFO
```

---

## 16. Prompt Templates

All LLM prompts are defined in `app/utils/prompts.py`. No hardcoded prompts exist elsewhere.

| Function | Used in | Output |
|----------|---------|--------|
| `build_decomposition_prompt()` | Orchestrator Step 2 | Structured JSON: intent, sql_filters, vector_query, ui_preference |
| `build_evaluation_prompt()` | Orchestrator Step 4 | JSON array of restaurant scores (5 dimensions) |
| `build_profiler_prompt()` | Profiler background task | JSON: preference signals (no allergy fields ever) |
| `build_user_context()` | Both Gemma prompts | Human-readable preference string |
| `build_allergy_context()` | Both Gemma prompts | Safety-critical allergy string with ⚠️ anaphylactic callout |

The decomposition and evaluation prompts always include:
- A `## SAFETY — USER ALLERGIES` section that cannot be skipped
- `anaphylactic` allergens explicitly listed for `exclude_allergens`
- The instruction: **"Output only valid JSON. No markdown fences. No preamble."**

---

## 17. Data Ingestion Pipeline

Located in `scripts/ingest.py`. Run once (or re-run to refresh data).

```
Zomato Bangalore CSV
  │
  ├─ Parse & clean each row
  │     - Normalise cuisine types → lowercase
  │     - Map cost_for_two → price_tier ($, $$, $$$, $$$$)
  │     - Infer allergens from cuisine types via CUISINE_ALLERGEN_MAP
  │       (confidence = "medium" for heuristic, "high" for explicit data)
  │
  ├─ Upsert into `restaurants` table
  │
  ├─ For each restaurant with reviews:
  │     - Call embed_texts([review_text, ...]) in batches
  │     - Insert into `reviews` table with embedding Vector(768)
  │
  └─ Build ivfflat index on reviews.embedding
       (required for pgvector ANN search performance)
```

Run with:
```bash
bash run_ingest.sh
```

---

## Architecture Decision Log

| Decision | Rationale |
|----------|-----------|
| **Allergies never inferred from chat** | Safety-critical — only explicit user action via Backend PATCH endpoint updates allergies |
| **Anaphylactic hard SQL filter** | AllergyGuard annotation is not enough — anaphylactic allergens are excluded at the DB query level before any LLM sees them |
| **Module-level AllergyGuard singleton** | Stateless — no benefit to per-request instantiation; avoids repeated initialisation overhead |
| **Background tasks use fresh sessions** | The request DB session may be closed before fire-and-forget tasks run |
| **Primary 30s / Fallback 60s timeout** | Gemini is fast; Gemma-3-12b needs more inference time. Asymmetric timeouts prevent premature fallback failures |
| **Profiler cannot touch allergies** | Explicit `_ALLOWED_PREFERENCE_KEYS` allowlist — even if LLM returns allergy keys, they are stripped before DB write |
| **DISTINCT ON + pgvector** | A restaurant may have multiple reviews; DISTINCT prevents duplication while still using the most recent embedded review for ranking |
