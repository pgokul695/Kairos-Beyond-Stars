# Kairos Agent — Complete Architecture Overview

> Last updated: 2026-02-27. Reflects production codebase including Recommendation System and full Frontend integration.

---

## Table of Contents

1. [Platform Context](#1-platform-context)
2. [Directory Structure](#2-directory-structure)
3. [API Surface](#3-api-surface)
4. [Request Lifecycle — POST /chat](#4-request-lifecycle--post-chat)
5. [The ReAct Orchestrator Loop](#5-the-react-orchestrator-loop)
6. [LLM Chain — Primary & Fallback](#6-llm-chain--primary--fallback)
7. [Embedding Pipeline](#7-embedding-pipeline)
8. [Hybrid Search](#8-hybrid-search)
9. [AllergyGuard — Safety Layer](#9-allergyguard--safety-layer)
10. [Generative UI Payload](#10-generative-ui-payload)
11. [Recommendation System](#11-recommendation-system)
12. [Frontend Integration Guide](#12-frontend-integration-guide)
13. [Data Model](#13-data-model)
14. [Authentication Model](#14-authentication-model)
15. [Caching Strategy](#15-caching-strategy)
16. [Background Tasks](#16-background-tasks)
17. [Startup Sequence](#17-startup-sequence)
18. [Configuration Reference](#18-configuration-reference)
19. [Prompt Templates](#19-prompt-templates)
20. [Data Ingestion Pipeline](#20-data-ingestion-pipeline)
21. [Architecture Decision Log](#21-architecture-decision-log)

---

## 1. Platform Context

The Kairos platform has four independent modules:

```mermaid
graph TD
    FE["Frontend\n(Next.js · port 3000)"]
    BE["Backend\n(Django · port 8000)"]
    AG["Agent\n(FastAPI · port 4021)"]
    MAIL["Mail Service"]
    PG[("PostgreSQL\nlocalhost:5433/vectordb")]

    FE -- "POST /chat\nGET /recommendations/{uid}\nX-User-ID header" --> AG
    BE -- "POST /users/{uid}\nPATCH allergies\nX-Service-Token header" --> AG
    AG <--> PG
    BE <--> PG
    BE --> MAIL
```

- **Frontend** calls `POST /chat` and `GET /recommendations/{uid}` passing `X-User-ID: <uid>` (received from Backend at login)
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
│   │   ├── user.py             # UserCreate, UserUpdate, AllergyUpdate, UserOut
│   │   └── recommendation.py   # NEW — FitTag, RecommendationItem, RecommendationPayload,
│   │                           #   ExpandedDetail, UserProfile (9 Pydantic models)
│   │
│   ├── routers/
│   │   ├── chat.py             # POST /chat — SSE stream, X-User-ID auth
│   │   ├── health.py           # GET /health, GET /ready
│   │   ├── users.py            # CRUD /users/{uid}, X-Service-Token auth
│   │   └── recommendations.py  # NEW — GET /recommendations/{uid}, GET .../expand
│   │
│   ├── services/
│   │   ├── orchestrator.py     # ReAct loop — the core Agent brain
│   │   ├── gemma.py            # LLM wrapper — primary + fallback model chain
│   │   ├── embedding.py        # Embedding client (gemini-embedding-001, 768d)
│   │   ├── hybrid_search.py    # SQL + pgvector cosine similarity search
│   │   ├── allergy_guard.py    # Safety layer — annotate + sort + flag restaurants
│   │   ├── profiler.py         # Background preference extractor (never touches allergies)
│   │   ├── fit_scorer.py       # NEW — pure Python algorithmic scorer (zero LLM/DB)
│   │   └── recommendation_service.py  # NEW — 7-step pipeline, TTLCache, prewarm
│   │
│   └── utils/
│       ├── prompts.py          # All LLM prompt builders (incl. 2 new recommendation builders)
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

Frontend/
└── components/
    └── RecommendationFeed.jsx  # NEW — personalised recommendation UI component
```

---

## 3. API Surface

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | None | Liveness check — always 200 |
| `GET`  | `/ready` | None | Readiness check — DB + embedding API |
| `POST` | `/chat` | `X-User-ID` | Streaming SSE chat endpoint |
| `GET`  | `/recommendations/{uid}` | `X-User-ID` | Ranked personalised feed (cached 24 h) |
| `GET`  | `/recommendations/{uid}/{restaurant_id}/expand` | `X-User-ID` | Lazy-loaded rich detail card |
| `POST` | `/users/{uid}` | `X-Service-Token` | Create user profile |
| `GET`  | `/users/{uid}` | `X-Service-Token` | Get user profile |
| `PATCH`| `/users/{uid}` | `X-Service-Token` | Update user preferences |
| `PATCH`| `/users/{uid}/allergies` | `X-Service-Token` | Update allergy profile |
| `DELETE`| `/users/{uid}` | `X-Service-Token` | Delete user + cascade |
| `DELETE`| `/users/{uid}/allergies` | `X-Service-Token` | Clear allergy data |

### Query parameters for `/recommendations/{uid}`

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `10` | Number of results, 1–25 |
| `refresh` | bool | `false` | Force cache invalidation and regenerate |

### Headers

| Header | Used by | Purpose |
|--------|---------|---------|
| `X-User-ID` | Frontend | UUID v4 — identifies the authenticated user |
| `X-Service-Token` | Backend | Shared secret (`KairosTest`) for server-to-server calls |

---

## 4. Request Lifecycle — POST /chat

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant Router as chat.py router
    participant Orch as orchestrator.py
    participant LLM as Gemma (gemini-2.5-flash)
    participant DB as PostgreSQL

    FE->>Router: POST /chat  X-User-ID: <uuid>
    Router->>Orch: orchestrate(uid, message, history, db)
    Orch-->>FE: SSE: thinking {step: fetching_context}
    Orch->>DB: SELECT user context
    Orch-->>FE: SSE: thinking {step: decomposing}
    Orch->>LLM: decomposition prompt → JSON filters
    LLM-->>Orch: {intent, sql_filters, vector_query}
    Orch-->>FE: SSE: thinking {step: searching}
    Orch->>DB: hybrid_search (SQL + pgvector)
    DB-->>Orch: up to 15 candidates
    Orch-->>FE: SSE: thinking {step: evaluating}
    Orch->>LLM: evaluation prompt → 5-dimension scores
    LLM-->>Orch: [{restaurant_id, scores...}]
    Orch-->>FE: SSE: thinking {step: checking_allergies}
    Orch->>Orch: AllergyGuard.check()
    Orch-->>FE: SSE: result {GenerativeUIPayload}
    Note over Orch: Stream closes
    Orch->>DB: async _save_interaction()
    Orch->>DB: async _run_profiler() + prewarm_recommendations()
```

---

## 5. The ReAct Orchestrator Loop

Located in `app/services/orchestrator.py`. The function `orchestrate()` is an `async generator` that yields SSE-formatted strings.

```mermaid
flowchart TD
    A[Receive message] --> B[Step 1: Fetch user context]
    B --> C[Step 2: Decompose query — Gemma #1]
    C --> D{needs_clarification?}
    D -- yes --> E[Yield SSE: text payload\nwith clarification question]
    D -- no --> F[Step 3: hybrid_search up to 15 candidates]
    F --> G{results > 0?}
    G -- no --> H[Yield SSE: text payload — no results found]
    G -- yes --> I[Step 4: Score top 10 — Gemma #2\n5 dimensions x 0–10]
    I --> J[Sort by composite score, take top 5]
    J --> K[Step 5: AllergyGuard.check]
    K --> L[Build GenerativeUIPayload]
    L --> M[Yield SSE: result payload]
    M --> N[Background: _save_interaction\n+ _run_profiler\n+ prewarm_recommendations]
```

**Auto-deliver on first hit:** Once `hybrid_search` returns results > 0, the orchestrator immediately evaluates, runs AllergyGuard, and yields the `result` event. It does **not** re-invoke the planner — this prevents infinite search-widening loops.

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

```mermaid
flowchart LR
    IN[call_gemma_json\nprompt] --> P[gemini-2.5-flash\ntimeout 30s]
    P -- success --> OUT[return parsed JSON]
    P -- any exception --> FB[gemma-3-12b-it\ntimeout 60s]
    FB -- success --> LOG[log info] --> OUT
    FB -- exception --> ERR[raise GemmaError]
```

```
call_gemma_json(prompt)
  │
  ├─ call_gemma(prompt) → raw text
  ├─ _strip_fences(raw)  — removes ```json ... ``` markdown
  └─ json.loads(cleaned) → Any  (raises GemmaError on parse fail)
```
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

```mermaid
flowchart TD
    A[hybrid_search called] --> B[embed_single vector_query]
    B --> C[Build dynamic WHERE clause\nfrom sql_filters]
    C --> D["price_tiers → ANY(:price_tiers)\ncuisine_types → && :cuisine_types\narea → ILIKE\nmin_rating → >=\nexclude_allergens → NOT && ← HARD FILTER"]
    D --> E["JOIN reviews — latest embedding per restaurant\nORDER BY cosine distance ASC, rating DESC\nDISTINCT ON restaurant.id"]
    E --> F[Return list RestaurantResult up to 15]
```

**Price tier normalisation (bug fix applied):**
```python
_TIER_MAP = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
# LLM integer values are silently coerced to strings before building the SQL query
```

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

## 11. Recommendation System

The Recommendation System is a **separate, non-chat pathway** that generates a personalised ranked feed proactively. It is purely JSON (not SSE) and cached per user per calendar day.

### Pipeline Overview

```mermaid
flowchart TD
    FE["Frontend\nRecommendationFeed.jsx"] -- "GET /recommendations/{uid}" --> RR["recommendations.py router"]
    RR --> RS["recommendation_service.py\nget_recommendations()"]
    RS --> CACHE{"TTLCache hit?\nkey = sha256(uid + date.today())"}
    CACHE -- hit --> RET["Return cached RecommendationPayload"]
    CACHE -- miss --> P1["Step 1\nFetch UserProfile from DB"]
    P1 --> P2["Step 2\nCandidate SQL — top 50 by rating\n+ anaphylactic hard filter"]
    P2 --> P3["Step 3\nFitScorer on all 50\n(pure Python, zero LLM)"]
    P3 --> P4["Step 4\nSort fit_score DESC\ntake top limit"]
    P4 --> P5["Step 5\nAllergyGuard.check()"]
    P5 --> P6["Step 6\nBatch LLM call\nconsolidated_review x N restaurants"]
    P6 --> P7["Step 7\nAssemble RecommendationPayload\nStore in TTLCache"]
    P7 --> RET

    FEX["Frontend — user taps card"] -- "GET /recommendations/{uid}/{id}/expand" --> RR2["recommendations.py router"]
    RR2 --> EX["get_expanded_detail()\nAlways fresh — not cached\n1 LLM call per restaurant"]
    EX --> RET2["ExpandedDetailResponse"]
```

### FitScorer — Pure Algorithmic Scoring

Located in `app/services/fit_scorer.py`. Zero LLM calls, zero DB calls. Runs on up to 50 candidates per request.

```mermaid
pie title FitScore Dimension Weights (100 pts total)
    "Cuisine affinity" : 30
    "Vibe match" : 25
    "Price comfort" : 20
    "Dietary compatibility" : 15
    "Allergy safety" : 10
```

| Dimension | Max pts | Logic |
|-----------|---------|-------|
| Cuisine | 30 | +30 full overlap, +15 partial, −10 aversion match |
| Vibe | 25 | +5 per matching vibe tag from `restaurant.meta`, capped 25 |
| Price | 20 | +20 exact tier, +10 one tier adjacent, 0 otherwise |
| Dietary | 15 | +5 per matching dietary flag, capped 15 |
| Allergy | 10 | +10 fully safe, +5 intolerance-only, 0 severe/anaphylactic |

**FitTag label templates (no LLM — template strings only):**

| Type | Label |
|------|-------|
| `cuisine` | `"Matches your {Cuisine} preference"` |
| `vibe` | `"Known for {vibe} — your top vibe tag"` |
| `price` | `"Within your {tier} comfort zone"` |
| `dietary` | `"{Flag}-friendly"` |
| `allergy_safe` | `"Safe for your allergy profile"` |

Tags capped at 4, sorted by dimension points descending — highest-value match shown first.

### Recommendation Schemas

```mermaid
classDiagram
    class RecommendationPayload {
        uid: str
        generated_at: datetime
        recommendations: list~RecommendationItem~
    }
    class RecommendationItem {
        rank: int
        fit_score: int
        fit_tags: list~FitTag~
        consolidated_review: str
        allergy_summary: AllergySummary
        expanded_detail: Optional~ExpandedDetail~
        restaurant: RestaurantResult
    }
    class ExpandedDetail {
        review_summary: str
        highlights: list~Highlight~
        crowd_profile: str
        best_for: list~str~
        avoid_if: list~str~
        radar_scores: RadarScores
        why_fit_paragraph: str
        allergy_detail: AllergyDetail
    }
    class FitTag {
        label: str
        type: cuisine|vibe|price|dietary|allergy_safe
    }
    class AllergySummary {
        is_safe: bool
        warnings: list~AllergyWarning~
    }
    RecommendationPayload --> RecommendationItem
    RecommendationItem --> FitTag
    RecommendationItem --> AllergySummary
    RecommendationItem --> ExpandedDetail
```

### Pre-warming

After the profiler writes new preferences to DB it fires a background task to warm the cache:

```python
# profiler.py — after successful db.commit()
from app.services.recommendation_service import prewarm_recommendations
asyncio.create_task(prewarm_recommendations(uid))
```

`prewarm_recommendations()` opens its own `AsyncSessionLocal()` and calls `get_recommendations(refresh=True)` — cache reflects updated preferences before the user opens the feed.

---

## 12. Frontend Integration Guide

### Full Feature Map

```mermaid
graph LR
    subgraph "Frontend Components"
        RF["RecommendationFeed.jsx\ncomponents/RecommendationFeed.jsx"]
        RC["RecommendationCard\ncollapsed"]
        EP["ExpandedPanel\nlazy"]
        SK["Skeleton loaders\nCardSkeleton / ExpandedSkeleton"]
    end

    subgraph "Agent Endpoints"
        R1["GET /recommendations/{uid}\n?limit=10&refresh=false"]
        R2["GET /recommendations/{uid}/{id}/expand"]
        C1["POST /chat"]
    end

    subgraph "Agent Services"
        RSV["recommendation_service"]
        ORCH["orchestrator (SSE stream)"]
    end

    RF --> R1
    RF --> RC
    RC --> EP
    EP --> R2
    R1 --> RSV
    R2 --> RSV
    C1 --> ORCH
```

### Component Tree

```
RecommendationFeed  (root export)
│   Props: uid, apiBase
│   State: recommendations[], loading, refreshing, error
│
├─ [loading=true]  → 3 × CardSkeleton  (pulsing placeholder)
├─ [error]         → error message + "Try again" retry button
├─ [empty]         → empty state message
│
└─ [loaded]
    ├─ Header: "Picked for you" + Refresh button (with spinner icon)
    │
    └─ map(recommendations) → RecommendationCard
          Props: item, uid, apiBase
          State: expanded, expandedDetail, expandLoading, expandError
          │
          ├─ [collapsed]
          │   ├─ FitScore badge    circular, colour by score tier
          │   ├─ Rank badge        dark circle, 1-based rank number
          │   ├─ Restaurant name + ★ rating
          │   ├─ Cuisine · Location · Price tier
          │   ├─ FitTag pills      icon + label, up to 4
          │   ├─ Consolidated review  ≤160 chars
          │   ├─ AllergyWarningBanner × N  severity-coloured banners
          │   ├─ Chevron ▼         rotates 180° when expanded
          │   └─ "Open on Zomato ↗"  stopPropagation, external link
          │
          └─ [expanded — maxHeight 0 → 1200px CSS transition]
              └─ ExpandedPanel
                  ├─ [expandLoading=true]  → ExpandedSkeleton
                  ├─ [expandError]         → error text
                  └─ [loaded]
                      ├─ Why it fits        italic blockquote (why_fit_paragraph)
                      ├─ Highlights         emoji + title + description
                      ├─ What people say    review_summary
                      ├─ Vibe scores        recharts RadarChart, 5 axes
                      ├─ Best for pills     emerald-50 background
                      ├─ Avoid if pills     red-50 background
                      ├─ Crowd profile      crowd_profile text
                      └─ Allergy breakdown  allergy_detail summary + recommendations
```

### Data Flow — Full Lifecycle

```mermaid
sequenceDiagram
    participant FE as RecommendationFeed
    participant A as Agent /recommendations/{uid}
    participant EX as Agent /expand

    FE->>A: GET /recommendations/{uid}?limit=10<br/>X-User-ID: uuid
    A-->>FE: RecommendationPayload JSON

    Note over FE: renders collapsed RecommendationCard list

    FE->>A: GET /recommendations/{uid}?refresh=true
    A-->>FE: Fresh RecommendationPayload (cache bypassed)

    Note over FE: User taps a card — expanded = true

    FE->>EX: GET /recommendations/{uid}/{restaurant_id}/expand<br/>X-User-ID: uuid
    EX-->>FE: ExpandedDetailResponse

    Note over FE: expandedDetail stored in card local state<br/>Re-opening card = no re-fetch
```

### FitScore Colour Mapping

| Score | Colour | Hex | Badge + RadarChart fill |
|-------|--------|-----|------------------------|
| ≥ 80 | Green | `#22c55e` | Excellent match |
| 60–79 | Amber | `#f59e0b` | Good match |
| < 60 | Grey | `#6b7280` | Partial match |

The same hex is reused as `stroke` / `fill` in the `RadarChart` — tying the visual theme to fit quality.

### AllergyWarningBanner Severity Colours

| Severity | Icon | Tailwind (light) | Dark mode |
|----------|------|-----------------|-----------|
| `danger` | 🚨 | `bg-red-50 border-red-300 text-red-800` | `dark:bg-red-950 ...` |
| `warning` | ⚠️ | `bg-amber-50 border-amber-300 text-amber-800` | `dark:bg-amber-950 ...` |
| `caution` | ⚡ | `bg-yellow-50 border-yellow-300 text-yellow-800` | `dark:bg-yellow-950 ...` |
| `info` | ℹ️ | `bg-blue-50 border-blue-300 text-blue-800` | `dark:bg-blue-950 ...` |

### Radar Chart Configuration

| Setting | Value |
|---------|-------|
| Library | `recharts` — `RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis` |
| Axes | Romance · Quiet · Food · Vegan · Value |
| Domain | `[0, 10]` (raw `radar_scores` from Agent) |
| Fill colour | `fitScoreHex` (green / amber / grey) |
| Fill opacity | `0.25` |
| Container | `h-44`, `ResponsiveContainer width="100%"` |

### FitTag Icons

| Type | Icon |
|------|------|
| `cuisine` | 🍴 |
| `vibe` | ✨ |
| `price` | 💰 |
| `dietary` | 🌿 |
| `allergy_safe` | ✅ |

### Props Contract

```typescript
interface RecommendationFeedProps {
  uid: string;      // UUID v4 — current authenticated user (from Backend JWT)
  apiBase: string;  // e.g. "http://localhost:4021" — no trailing slash
}

// Usage
<RecommendationFeed
  uid={currentUser.id}
  apiBase={process.env.NEXT_PUBLIC_AGENT_URL}
/>
```

### Expand Fetch Behaviour

```mermaid
flowchart TD
    TAP[User taps card] --> EXP[expanded = true]
    EXP --> CHECK{expandedDetail !== null?}
    CHECK -- yes --> RENDER[Render immediately\nfrom local state cache]
    CHECK -- no --> FETCH[Fire GET /expand fetch]
    FETCH --> LOAD[setExpandLoading true]
    LOAD --> SUCCESS[setExpandedDetail data]
    SUCCESS --> RENDER
    CLOSE[User closes card] --> REOPEN[User reopens]
    REOPEN --> CHECK
```

Each restaurant's detail is fetched **at most once per component mount** — result is cached in component state.

### Frontend Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `recharts` | Radar chart in ExpandedPanel | `npm install recharts` |
| `react` (hooks) | `useState`, `useEffect`, `useCallback` | ✅ Next.js |
| Tailwind CSS | All styling — no custom CSS | ✅ Next.js config |

---

## 13. Data Model

Four tables in PostgreSQL (`vectordb`):

### Entity Relationship

```mermaid
erDiagram
    users {
        UUID uid PK
        JSONB preferences
        JSONB allergies
        TEXT_ARRAY allergy_flags
        TEXT_ARRAY dietary_flags
        TEXT_ARRAY vibe_tags
        TEXT_ARRAY preferred_price_tiers
        INT interaction_count
        TIMESTAMP last_active_at
    }
    restaurants {
        INT id PK
        TEXT name
        TEXT_ARRAY cuisine_types
        VARCHAR price_tier
        INT cost_for_two
        NUMERIC rating
        TEXT_ARRAY known_allergens
        VARCHAR allergen_confidence
        DOUBLE lat
        DOUBLE lng
        JSONB meta
        BOOLEAN is_active
    }
    reviews {
        INT id PK
        INT restaurant_id FK
        TEXT text
        VECTOR_768 embedding
    }
    interactions {
        UUID id PK
        UUID uid FK
        TEXT user_query
        JSONB agent_response
        VARCHAR ui_type
        INT_ARRAY restaurant_ids
        BOOLEAN allergy_warnings_shown
        TEXT_ARRAY allergens_flagged
        TIMESTAMP created_at
    }

    users ||--o{ interactions : "uid"
    restaurants ||--o{ reviews : "restaurant_id"
```

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

## 14. Authentication Model

The Agent uses **two separate authentication schemes** — one per caller:

```mermaid
flowchart LR
    subgraph "Frontend caller"
        FE["Frontend\n(Next.js)"] -- "X-User-ID: UUID\n/chat, /recommendations" --> AG["Agent\n(FastAPI)"]
    end
    subgraph "Backend caller"
        BE["Backend\n(Django)"] -- "X-Service-Token: KairosTest\n/users/..." --> AG
    end
```

### Frontend → Agent: `X-User-ID`

```
Frontend (already has JWT from Backend)
  │
  │  POST /chat
  │  X-User-ID: <uid>   ← UUID extracted from JWT by Frontend
  │
  ▼
Agent validates UUID format only.
JWT verification is the Backend's responsibility — Agent trusts the header. Path `{uid}` must match `X-User-ID` header; mismatch returns `403 Forbidden`.
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

## 15. Caching Strategy

Three TTL caches are active at module-level (never per-request, using `cachetools.TTLCache`):

```mermaid
graph LR
    DC["_cache_decomp\nmaxsize=200, TTL=3600s\nkey: sha256(uid+message)\nOrchestrator decomposition"]
    SC["_cache_search\nmaxsize=500, TTL=1800s\nkey: sha256(sql_filters+vector_query)\nHybrid search results"]
    RC["_cache_recommendations\nmaxsize=1000, TTL=86400s\nkey: sha256(uid+date.today())\nPersonalised recommendation feed"]
```

| Cache | Module | Key | TTL | Notes |
|-------|--------|-----|-----|-------|
| `_cache_decomp` | `orchestrator.py` | `sha256(uid + message)` | 1 h | Prevents duplicate LLM decomposition calls for identical messages |
| `_cache_search` | `hybrid_search.py` | `sha256(sql_filters + vector_query)` | 30 min | Prevents duplicate DB + embedding calls for identical search params |
| `_cache_recommendations` | `recommendation_service.py` | `sha256(uid + date.today())` | 24 h | Auto-expires at midnight; `?refresh=true` invalidates early |

No Redis dependency — purely in-process memory.

---

## 16. Background Tasks

After the SSE stream closes, **three** `asyncio.create_task()` fire-and-forget tasks run. Each opens its own `AsyncSessionLocal()` session.

```mermaid
flowchart TD
    STREAM["SSE stream closes\n(result event yielded)"] --> T1 & T2
    T2 --> T3

    T1["_save_interaction()\nInserts into interactions table\nResponse serialised via json.dumps()"]
    T2["_run_profiler()\nGemma call — extract preference signals\nUpdates preferences, dietary_flags, vibe_tags\nAllergies are NEVER inferred from chat"]
    T3["prewarm_recommendations(uid)\nFire-and-forget after profiler write\nCalls get_recommendations(refresh=True)\nOpens its own AsyncSessionLocal()"]
```

### `_save_interaction(uid, message, payload, restaurant_ids, allergens_flagged, has_warnings)`

Inserts into `interactions` table. `agent_response` column serialised via `json.dumps(payload.model_dump())` — prevents `asyncpg` JSONB encoding error with raw Python dicts. Never raises.

### `_run_profiler(uid, message, payload_dict)`

Calls `update_user_profile()` from `app/services/profiler.py`.

The profiler:
1. Calls `call_gemma_json(profiler_prompt)` to extract preference signals
2. Sanitises output — strips any allergy-related keys (allergies are **never** inferred from chat)
3. Deep-merges lists (union + deduplicate), replaces scalar values
4. Updates `users.preferences` (serialised via `json.dumps(current_prefs)`), `dietary_flags`, `vibe_tags`, `interaction_count`, `last_active_at`
5. On success → fires `prewarm_recommendations(uid)` as a nested `asyncio.create_task()`
6. If Gemma fails OR no new preferences found: bumps `interaction_count` only

**Allowed preference keys:**
```python
_ALLOWED_PREFERENCE_KEYS = {
    "dietary", "vibes", "cuisine_affinity", "cuisine_aversion", "price_comfort"
}
```

---

## 17. Startup Sequence

Handled by the FastAPI `lifespan` context manager in `app/main.py`:

```mermaid
flowchart TD
    S["uvicorn starts\n(run.sh, port 4021)"] --> E1
    E1["CREATE EXTENSION IF NOT EXISTS vector"] --> E2
    E2["Base.metadata.create_all\n(users, restaurants, reviews, interactions\n+ ivfflat index on reviews.embedding)"] --> E3
    E3["SELECT 1 — DB connectivity check"] --> READY["App accepting traffic"]
    READY --> CORS["CORS configured\nsettings.allowed_origins_list"]
    READY --> ROUTERS["Routers registered:\n/chat  /health  /recommendations  /users"]
```

CORS is configured with `settings.allowed_origins_list` (comma-split from `ALLOWED_ORIGINS` env var).

---

## 18. Configuration Reference

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

## 19. Prompt Templates

All LLM prompts are defined in `app/utils/prompts.py`. No hardcoded prompts exist elsewhere.

| Function | Used in | Output |
|----------|---------|--------|
| `build_decomposition_prompt()` | Orchestrator Step 2 | Structured JSON: intent, sql_filters, vector_query, ui_preference |
| `build_evaluation_prompt()` | Orchestrator Step 4 | JSON array of restaurant scores (5 dimensions) |
| `build_profiler_prompt()` | Profiler background task | JSON: preference signals (no allergy fields ever) |
| `build_user_context()` | All LLM prompts | Human-readable preference string |
| `build_allergy_context()` | All LLM prompts | Safety-critical allergy string with ⚠️ anaphylactic callout |
| `build_fit_explanation_prompt()` | Recommendation service Step 6 | JSON array `[{restaurant_id, consolidated_review}]` — one call for all N restaurants |
| `build_expand_detail_prompt()` | `get_expanded_detail()` | Single restaurant full `ExpandedDetail` JSON — reviews + user context |

All prompts include a `## SAFETY — USER ALLERGIES` section and end with:
> **"Output only valid JSON. No markdown fences. No preamble."****

---

## 20. Data Ingestion Pipeline

Located in `scripts/ingest.py`. Run once (or re-run to refresh data).

```mermaid
flowchart TD
    CSV["data/zomato.csv"] --> PARSE["Parse & clean each row\n- Normalise cuisine types → lowercase\n- cost_for_two → price_tier\ $..$$$$\n- Infer allergens from CUISINE_ALLERGEN_MAP\n  confidence = medium for heuristic"]
    PARSE --> UPSERT["Upsert into restaurants table"]
    UPSERT --> EMBED["For each restaurant with reviews:\nembed_texts in batches\n(gemini-embedding-001, 768d)"]
    EMBED --> INSERT["Insert into reviews table\nwith Vector(768) embedding"]
    INSERT --> INDEX["Build ivfflat index\non reviews.embedding\n(required for pgvector ANN search)"]
```

Run with:
```bash
bash run_ingest.sh
# or directly:
source .venv/bin/activate && python scripts/ingest.py --csv data/zomato.csv --limit 500
```

> ⚠️ **Note:** The database must be populated before `/chat` or `/recommendations` can return results. Run ingest before testing.

---

## 21. Architecture Decision Log

| Decision | Rationale |
|----------|-----------|
| **Allergies never inferred from chat** | Safety-critical — only explicit user action via Backend PATCH endpoint updates allergies |
| **Anaphylactic hard SQL filter** | AllergyGuard annotation is not enough — anaphylactic allergens are excluded at the DB query level before any LLM sees them |
| **Module-level AllergyGuard + FitScorer singletons** | Stateless — no benefit to per-request instantiation; avoids repeated initialisation overhead |
| **Background tasks use fresh sessions** | The request DB session may be closed before fire-and-forget tasks run |
| **Primary 30s / Fallback 60s timeout** | Gemini is fast; Gemma-3-12b needs more inference time. Asymmetric timeouts prevent premature fallback failures |
| **Profiler cannot touch allergies** | Explicit `_ALLOWED_PREFERENCE_KEYS` allowlist — even if LLM returns allergy keys, they are stripped before DB write |
| **DISTINCT ON + pgvector** | A restaurant may have multiple reviews; DISTINCT prevents duplication while still using the most recent embedded review for ranking |
| **FitScorer is pure Python** | Runs on 50 candidates per request; LLM latency would be unacceptable. Algorithmic scoring is deterministic, debuggable, and sub-millisecond |
| **Recommendation cache key = sha256(uid + date)** | Naturally invalidates at midnight without a scheduled job; `refresh=true` allows early invalidation |
| **Expand endpoint never cached** | Rich detail is per-restaurant + per-user context; the LLM call is the majority of latency. Frontend caches per card mount instead |
| **prewarm after profiler write** | Ensures the recommendation cache reflects fresh preferences immediately after the first chat turn that updates them |
| **RecommendationFeed expands lazily** | Network round-trip for /expand is ~500ms; fetching all cards eagerly would create visible lag. User intent (tapping) is the natural debounce |
| **JSONB serialised via json.dumps** | asyncpg does not encode raw Python dicts — `json.dumps()` passed as a string ensures correct JSONB binding for all JSONB columns (`preferences`, `agent_response`) |
| **Integer price_tiers coerced before SQL** | LLM occasionally returns integer price tier indices instead of string symbols; `_TIER_MAP` normalises silently rather than failing |
| **Auto-deliver on first search success** | Prevents the ReAct loop from calling `search_restaurants` 5× with widening filters when results are found on the first try |
