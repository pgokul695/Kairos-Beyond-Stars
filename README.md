# 🌌 KAIROS — Beyond Stars

> *AI-powered restaurant discovery and personalisation platform — where intelligent dining recommendations meet allergy safety.*

---

## 👥 Team

| Name | Role | Email |
|------|------|-------|
| Gokul P | AI Developer, Team Lead | me@gokulp.in |
| Keerthana Vinod | UI Designer | keerthanavinod567@gmail.com |
| Arpitha Bhandary | QA | mearpithabhandary@gmail.com |
| C Ranita Nazrine | UX Developer | craniyanazrine321@gmail.com |

---

## 📋 Table of Contents

1. [Project Overview](#-project-overview)
2. [System Architecture](#-system-architecture)
3. [Repository Structure](#-repository-structure)
4. [Tech Stack](#-tech-stack)
5. [Data Flow](#-data-flow)
6. [Getting Started](#-getting-started)
   - [Prerequisites](#prerequisites)
   - [Environment Setup](#environment-setup-enveexample-explained)
   - [Installation](#installation)
   - [Running with Docker](#running-with-docker)
   - [Running Locally](#running-locally)
7. [Agent Module](#-agent-module)
8. [Backend Module](#-backend-module)
9. [Frontend Module](#-frontend-module)
10. [Testing & QA](#-testing--qa)
11. [Agent ↔ Backend Integration](#-agent--backend-integration)
12. [Deployment](#-deployment)
13. [Contributing](#-contributing)
14. [License](#-license)

---

## 🧭 Project Overview

**Kairos — Beyond Stars** is a full-stack AI dining concierge platform specifically built for the Bangalore restaurant ecosystem. The system combines a conversational AI agent, a personalisation engine, and a safety-critical allergy guard to help users discover restaurants that match their taste, mood, dietary restrictions, and budget.

The platform is structured as three independent modules: a **FastAPI-based AI Agent** that powers natural language search and personalised recommendations, a **Django REST Framework Backend** that handles user authentication and account management, and a **React/Vite Frontend** that delivers a polished, responsive UI. All three communicate via well-defined API contracts, allowing each module to be developed, deployed, and scaled independently.

The core intelligence lives in the Agent, which executes a five-step reasoning loop on every chat query: context retrieval → query decomposition (Gemma LLM) → hybrid SQL + pgvector search → LLM evaluation → AllergyGuard safety filtering → streamed Generative UI response. User preferences are learned automatically from every conversation turn by a background profiler that is deliberately prevented from touching allergy data.

---

## 🏗️ System Architecture

```mermaid
graph TD
    User["👤 User (Browser)"]

    FE["🎨 Frontend\nReact + Vite\nport 3000"]
    BE["🖥️ Backend\nDjango 5.2 + DRF\nport 8000"]
    AG["🤖 Agent\nFastAPI + Uvicorn\nport 4021"]
    PG[("🐘 PostgreSQL + pgvector\nport 5432")]
    MAIL["📧 Mail Service\nSMTP"]
    GOOGLE["🔮 Google AI\nGemma-2 + Embeddings"]

    User -- "HTTP (browser)" --> FE
    FE -- "POST /api/signup\nPOST /api/login" --> BE
    FE -- "POST /chat\nGET /recommendations/{uid}\nX-User-ID header" --> AG
    BE -- "POST /users/{uid}\nPATCH /users/{uid}/allergies\nX-Service-Token header" --> AG
    BE --> MAIL
    AG <--> PG
    BE <--> PG
    AG --> GOOGLE
```

The Frontend communicates with both the Backend (for auth) and the Agent (for AI features) — there is no Backend hop for chat traffic. The Backend is the sole authority for identity management and forwards lifecycle events (signup, allergy update, deletion) to the Agent via an internal service token.

---

## 🗂️ Repository Structure

```
Kairos-Beyond-Stars/
│
├── README.md                          ← You are here — single source of truth
├── .env.example                       ← Documented environment variable template
├── .gitignore                         ← Git ignore rules for all submodules
│
├── Agent/                             ← FastAPI AI agent (port 4021)
│   ├── docker-compose.yml             ← Postgres + pgvector container definition
│   ├── requirements.txt               ← Python package dependencies
│   ├── run.sh                         ← Local dev launcher (creates venv, installs deps)
│   ├── run_ingest.sh                  ← Dataset ingestion launcher
│   ├── README.md                      ← Agent submodule documentation
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    ← FastAPI app, lifespan, CORS, router registration
│   │   ├── config.py                  ← Pydantic Settings — all env var bindings
│   │   ├── database.py                ← AsyncEngine, session factory, pgvector init
│   │   ├── models/
│   │   │   ├── user.py                ← User ORM (uid, preferences, allergies, flags)
│   │   │   ├── restaurant.py          ← Restaurant ORM (cuisines, allergens, meta)
│   │   │   ├── review.py              ← Review ORM with 768-dim Vector embedding
│   │   │   └── interaction.py         ← Interaction ORM (audit trail of every chat turn)
│   │   ├── routers/
│   │   │   ├── chat.py                ← POST /chat — SSE streaming endpoint
│   │   │   ├── health.py              ← GET /health, GET /ready — probes
│   │   │   ├── users.py               ← /users/* — service-token-protected CRUD
│   │   │   └── recommendations.py     ← GET /recommendations/{uid} — personalised feed
│   │   ├── schemas/
│   │   │   ├── chat.py                ← ChatRequest, ChatMessage Pydantic models
│   │   │   ├── restaurant.py          ← AllergyWarning, RadarScores, GenerativeUIPayload
│   │   │   ├── user.py                ← UserCreate, UserRead, AllergiesPatch, etc.
│   │   │   └── recommendation.py      ← FitTag, RecommendationItem, UserProfile, etc.
│   │   ├── services/
│   │   │   ├── orchestrator.py        ← 5-step ReAct reasoning loop (core AI logic)
│   │   │   ├── allergy_guard.py       ← Safety layer — annotates every result
│   │   │   ├── hybrid_search.py       ← SQL + pgvector cosine similarity search
│   │   │   ├── fit_scorer.py          ← Pure-Python 0–100 restaurant scorer
│   │   │   ├── gemma.py               ← Google Gemma-2 API wrapper with retry
│   │   │   ├── embedding.py           ← Google text-embedding-004 wrapper (batched)
│   │   │   ├── profiler.py            ← Background preference extractor (no allergy data)
│   │   │   ├── recommendation_service.py ← Recommendation feed builder with FitScorer
│   │   │   ├── chroma_client.py       ← ChromaDB singleton client (legacy/alt vector store)
│   │   │   └── local_ml.py            ← Local ML utilities
│   │   └── utils/
│   │       ├── allergy_data.py        ← Canonical allergen lists, synonyms, severity
│   │       └── prompts.py            ← All Gemma prompt templates (no hardcoding elsewhere)
│   ├── docs/
│   │   ├── ARCHITECTURE.md            ← Detailed Agent architecture reference
│   │   └── BACKEND_INTEGRATION_REPORT.md ← Frontend integration guide
│   └── scripts/
│       ├── ingest.py                  ← Zomato Bangalore dataset ingestion script
│       └── create_tables.py           ← Standalone table creation utility
│
├── Backend/                           ← Django 5.2 auth backend (port 8000)
│   ├── manage.py                      ← Django management entry point
│   ├── db.sqlite3                     ← SQLite database (development only)
│   ├── AGENT_INTEGRATION_REPORT.md    ← Integration guide for Backend ↔ Agent
│   ├── README.md                      ← Backend submodule documentation
│   ├── beyondstars_backend/
│   │   ├── settings.py                ← Django project settings
│   │   ├── urls.py                    ← Root URL dispatcher (admin + api/)
│   │   ├── asgi.py                    ← ASGI entry point
│   │   └── wsgi.py                    ← WSGI entry point
│   └── core/
│       ├── models.py                  ← User model (username, email, auth_token)
│       ├── views.py                   ← signup, login, verify_email API views
│       ├── serializers.py             ← UserSerializer (ModelSerializer)
│       ├── urls.py                    ← /signup/, /login/, /verify/<token>/
│       ├── admin.py                   ← Django admin registration
│       └── migrations/                ← Database migration files
│
└── Frontend/                          ← React 19 + Vite SPA (port 3000)
    ├── README.md                      ← Frontend submodule documentation
    └── beyond-stars/
        ├── package.json               ← Node.js dependencies and scripts
        ├── vite.config.js             ← Vite bundler configuration
        ├── tailwind.config.js         ← Tailwind CSS theme configuration
        ├── index.html                 ← HTML shell
        └── src/
            ├── App.jsx                ← Root component with router setup
            ├── main.jsx               ← React 19 entry point
            ├── components/
            │   ├── Navbar.jsx         ← Sticky navigation with mobile menu
            │   ├── SearchBar.jsx      ← AI-styled search with navigation
            │   ├── RestaurantCard.jsx ← Card with match score, image, tags
            │   ├── MapView.jsx        ← Interactive map panel (visual placeholder)
            │   ├── ComparisonChart.jsx ← Recharts radar/bar comparison widget
            │   ├── CircularProgress.jsx ← SVG circular score indicator
            │   ├── AIBadge.jsx        ← "AI Recommended" / "Top Match" badge
            │   └── PhotoGallery.jsx   ← Restaurant photo gallery carousel
            ├── pages/
            │   ├── Home.jsx           ← Hero landing page with animated particles
            │   ├── Results.jsx        ← Filterable, sortable restaurant grid
            │   └── RestaurantDetail.jsx ← Full restaurant detail with gallery
            └── data/
                └── dummyData.js       ← Mock restaurant data for UI development
```

---

## ⚙️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **AI Agent** | FastAPI 0.111 + Uvicorn | Async HTTP server and streaming SSE |
| **AI Agent** | SQLAlchemy 2.0 (asyncio) + asyncpg | Async ORM and PostgreSQL driver |
| **AI Agent** | pgvector 0.3 | 768-dim vector similarity search in Postgres |
| **AI Agent** | Google Gemma-2-9b-it | Natural language query decomposition and evaluation |
| **AI Agent** | Google text-embedding-004 | 768-dimensional semantic embeddings |
| **AI Agent** | Pydantic v2 + pydantic-settings | Schema validation and typed config |
| **AI Agent** | Tenacity | Retry logic for LLM and embedding API calls |
| **AI Agent** | ChromaDB | Alternative persistent vector store |
| **Backend** | Django 5.2 | Web framework and ORM |
| **Backend** | Django REST Framework | API serializers and views |
| **Backend** | SQLite (dev) | Development database |
| **Frontend** | React 19 | Component-based UI library |
| **Frontend** | Vite 7 | Fast build tool and dev server |
| **Frontend** | React Router v7 | Client-side routing |
| **Frontend** | Tailwind CSS v4 | Utility-first styling |
| **Frontend** | Recharts 3 | Data visualisation (radar, bar charts) |
| **Database** | PostgreSQL 16 + pgvector | Production vector-capable database |
| **Infra** | Docker + Docker Compose | Container orchestration |

---

## 🔄 Data Flow

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend (React)
    participant BE as Backend (Django)
    participant AG as Agent (FastAPI)
    participant PG as PostgreSQL + pgvector
    participant GG as Google AI (Gemma + Embeddings)

    Note over User,GG: ── Registration Flow ──
    User->>FE: Fill signup form
    FE->>BE: POST /api/signup/ {username, email, password}
    BE->>BE: Create User, generate auth_token (UUID)
    BE->>AG: POST /users/{auth_token} (X-Service-Token)
    AG->>PG: INSERT INTO users (uid, preferences={}, allergies={})
    BE->>User: Send verification email

    Note over User,GG: ── Login Flow ──
    User->>FE: Submit login credentials
    FE->>BE: POST /api/login/ {email, password}
    BE->>FE: {message: "Login successful", auth_id: "<uuid>"}
    FE->>FE: Store auth_id in local state

    Note over User,GG: ── Chat Flow ──
    User->>FE: Type query "romantic dinner Koramangala"
    FE->>AG: POST /chat {message, history} + X-User-ID header
    AG->>PG: SELECT preferences, allergies FROM users
    AG->>GG: Gemma call #1 — decompose query → JSON filters
    AG->>GG: embed_single(vector_query) → 768-dim vector
    AG->>PG: Hybrid SQL + vector search (cosine distance)
    AG->>GG: Gemma call #2 — evaluate + rank results
    AG->>AG: AllergyGuard.check() — annotate + sort safe-first
    AG->>AG: Profiler.update_user_profile() (background)
    AG-->>FE: SSE stream: thinking events + final GenerativeUIPayload
    FE->>User: Render restaurant cards / radar chart / map

    Note over User,GG: ── Recommendations Flow ──
    FE->>AG: GET /recommendations/{uid} (X-User-ID)
    AG->>PG: Load user profile (preferences, allergies, flags)
    AG->>PG: Candidate restaurants (up to 50)
    AG->>AG: FitScorer.score() — 0–100 per restaurant
    AG->>AG: AllergyGuard.check() — safety filter
    AG->>GG: Gemma — one-sentence review summary per restaurant
    AG-->>FE: RecommendationPayload (ranked, annotated)
```

---

## 🚀 Getting Started

### Prerequisites

Ensure the following are installed on your machine before proceeding:

- **Python 3.11+** — required for the Agent and Backend
- **Node.js 20+** with npm — required for the Frontend
- **Docker & Docker Compose** — required for the PostgreSQL + pgvector container
- **Google AI API Key** — obtain from [Google AI Studio](https://aistudio.google.com/app/apikey)

### Environment Setup (.env.example explained)

Copy `.env.example` to `Agent/.env` and fill in the required values. Every variable is documented below:

```bash
cp .env.example Agent/.env
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | ✅ | — | Full async Postgres URL: `postgresql+asyncpg://user:pass@host:5432/db` |
| `GOOGLE_API_KEY` | ✅ | — | Google AI Studio API key for Gemma and embeddings |
| `GEMMA_MODEL` | ❌ | `gemma-2-9b-it` | Gemma model identifier |
| `EMBEDDING_MODEL` | ❌ | `text-embedding-004` | Google embedding model identifier |
| `EMBEDDING_DIMENSIONS` | ❌ | `768` | Embedding vector dimensionality |
| `SERVICE_TOKEN` | ✅ | — | Shared secret for Backend → Agent inter-service calls |
| `ALLOWED_ORIGINS` | ❌ | `https://kairos.gokulp.online,http://localhost:3000` | Comma-separated CORS origins |
| `APP_ENV` | ❌ | `development` | `development` enables SQL echo and `--reload`; set `production` in prod |
| `LOG_LEVEL` | ❌ | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `POSTGRES_DB` | ✅ | — | Database name (used by Docker Compose) |
| `POSTGRES_USER` | ✅ | — | Database user (used by Docker Compose) |
| `POSTGRES_PASSWORD` | ✅ | — | Database password (used by Docker Compose) |

> ⚠️ **Warning:** Never commit your `.env` file or your `GOOGLE_API_KEY` to version control. The `.env.example` file contains only placeholder values and is safe to commit.

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/your-org/Kairos-Beyond-Stars.git
cd Kairos-Beyond-Stars
```

**2. Set up the Agent**

```bash
cd Agent
cp ../.env.example .env
# Edit .env with your credentials
./run.sh
```

**3. Set up the Backend**

```bash
cd ../Backend
python3 -m venv .venv
source .venv/bin/activate
pip install django djangorestframework
python manage.py migrate
python manage.py runserver 8000
```

**4. Set up the Frontend**

```bash
cd ../Frontend/beyond-stars
npm install
npm run dev
```

### Running with Docker

The `Agent/docker-compose.yml` file defines the PostgreSQL + pgvector container. The Agent application itself runs on the host (or can be containerised separately).

```bash
cd Agent
# Start the database
docker compose up -d

# Verify the container is healthy
docker compose ps
```

The `docker-compose.yml` configuration:

```yaml
version: '3.9'
services:
  db:
    image: pgvector/pgvector:pg16     # Official pgvector image with PostgreSQL 16
    container_name: kairos_agent_db
    environment:
      POSTGRES_DB: ${POSTGRES_DB}     # From your .env file
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"                   # Exposed on localhost:5432
    volumes:
      - pgdata:/var/lib/postgresql/data  # Persistent data volume
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

> ⚠️ **Warning:** The default port is `5432`. If you already have PostgreSQL running locally, either stop it first or change the host port mapping to `"5433:5432"` and update `DATABASE_URL` accordingly.

### Running Locally

**`run.sh` — Agent Server**

This script automates the complete local startup sequence:

1. Creates a Python virtualenv at `Agent/.venv` if it does not exist
2. Activates the virtualenv
3. Installs/upgrades all packages from `requirements.txt`
4. Exports all vars from `Agent/.env` into the shell environment
5. Starts Uvicorn (via Gunicorn in production) with hot-reload in development

```bash
cd Agent
chmod +x run.sh
./run.sh

# Override defaults with environment variables:
HOST=127.0.0.1 PORT=4021 WORKERS=4 APP_ENV=production ./run.sh
```

**`run_ingest.sh` — Dataset Ingestion**

This script ingests the Zomato Bangalore restaurant dataset into PostgreSQL. Run this once before starting the Agent for the first time.

```bash
# Step 1: Download the dataset from Kaggle
# https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
# Place the file at: Agent/data/zomato.csv

# Step 2: Run dry-run to verify parsing (no DB writes)
cd Agent
./run_ingest.sh

# Step 3: Run full ingestion
./run_ingest.sh --csv data/zomato.csv

# Step 4: Regenerate all embeddings (slow — calls Google API per review)
./run_ingest.sh --csv data/zomato.csv --re-embed

# Step 5: Re-run allergen tagging only (fast)
./run_ingest.sh --csv data/zomato.csv --retag-allergens
```

---

## 🤖 Agent Module

The Agent is the intelligence core of the Kairos platform. It delivers conversational restaurant discovery via a five-step AI reasoning loop, a personalisation system that learns from every interaction, a pure-Python fit scorer for algorithmic ranking, and a safety-critical AllergyGuard that annotates every result.

📖 **Full documentation:** [Agent/README.md](Agent/README.md)

```mermaid
flowchart TD
    A["POST /chat\n(user message + history)"] --> B["Step 1: Load User Context\npreferences, allergies, flags from DB"]
    B --> C["Step 2: Gemma #1 — Query Decomposition\nIntent · SQL filters · vector_query · ui_preference"]
    C --> D{"needs_clarification?"}
    D -- Yes --> E["Return clarification text\n(SSE result event)"]
    D -- No --> F["Step 3: Hybrid Search\nSQL WHERE + pgvector cosine distance"]
    F --> G["Step 4: Gemma #2 — Evaluation\nRank + annotate restaurant shortlist"]
    G --> H["Step 5: AllergyGuard\nAnnotate warnings · sort safest-first · flag anaphylactic"]
    H --> I["Stream GenerativeUIPayload\n(SSE result event)"]
    I --> J["Background: Profiler\nExtract preferences (never allergy data)"]
```

---

## 🖥️ Backend Module

The Backend handles all user identity operations: registration, email verification, and login. It generates the `auth_token` UUID that serves as the user's identity across the entire platform and synchronises user lifecycle events to the Agent via the internal service API.

📖 **Full documentation:** [Backend/README.md](Backend/README.md)

```mermaid
erDiagram
    USER {
        int id PK
        string username
        string email
        string password
        bool is_verified
        uuid auth_token
    }
```

```mermaid
graph LR
    R1["POST /api/signup/"]
    R2["POST /api/login/"]
    R3["GET /api/verify/{token}/"]
    R4["GET /admin/"]

    R1 --> V1["signup view"]
    R2 --> V2["login view"]
    R3 --> V3["verify_email view"]
    R4 --> V4["Django Admin"]

    V1 --> M["User model"]
    V2 --> M
    V3 --> M
```

---

## 🎨 Frontend Module

The Frontend delivers a polished, responsive dining discovery UI built with React 19, Vite, and Tailwind CSS. It features an AI-styled search bar, filterable restaurant card grids, an interactive map panel, radar-chart comparisons, and detailed restaurant pages with photo galleries.

📖 **Full documentation:** [Frontend/README.md](Frontend/README.md)

```mermaid
graph TD
    App["App.jsx\n(Router root)"]
    Navbar["Navbar.jsx"]
    Home["Home.jsx\n(Hero landing)"]
    Results["Results.jsx\n(Filterable grid)"]
    Detail["RestaurantDetail.jsx\n(Full detail)"]

    App --> Navbar
    App --> Home
    App --> Results
    App --> Detail

    Home --> SearchBar["SearchBar.jsx"]
    Results --> SearchBar
    Results --> RestaurantCard["RestaurantCard.jsx"]
    Results --> MapView["MapView.jsx"]
    Results --> ComparisonChart["ComparisonChart.jsx"]
    RestaurantCard --> CircularProgress["CircularProgress.jsx"]
    RestaurantCard --> AIBadge["AIBadge.jsx"]
    Detail --> PhotoGallery["PhotoGallery.jsx"]
    Detail --> ComparisonChart
    Detail --> CircularProgress
```

---

## 🧪 Testing & QA

Testing is a shared responsibility across all three modules. The QA owner (Arpitha Bhandary) coordinates test coverage requirements and acceptance criteria.

**Agent Testing**

The Agent exposes two readiness probes that serve as integration health checks. Run the readiness probe after starting the server to verify database and embedding API connectivity:

```bash
curl http://localhost:4021/health   # Liveness check
curl http://localhost:4021/ready    # Readiness check (DB + embedding API)
```

For unit testing the services, use `pytest` with `pytest-asyncio`:

```bash
cd Agent
source .venv/bin/activate
pip install pytest pytest-asyncio httpx
pytest tests/
```

**Backend Testing**

Use Django's built-in test runner:

```bash
cd Backend
python manage.py test core
```

**Frontend Testing**

The Vite project supports ESLint for static analysis:

```bash
cd Frontend/beyond-stars
npm run lint
npm run build  # Validates the production build succeeds
```

**QA Strategy**

End-to-end testing focuses on three critical paths:
1. **Registration → Verification → Login** — ensures the Backend correctly provisions the Agent user and returns the `auth_id`.
2. **Chat with allergen trigger** — ensures AllergyGuard correctly intercepts anaphylactic-severity allergen matches.
3. **Recommendation feed** — ensures FitScorer returns ranked, allergy-safe results within the 24-hour cache TTL.

> ⚠️ **Warning:** The allergy safety system is safety-critical. Any change to `AllergyGuard`, `allergy_data.py`, or the `sql_filters.exclude_allergens` pipeline must be reviewed and tested against the allergen test matrix before merging.

---

## 🔗 Agent ↔ Backend Integration

The Backend and Agent integrate through a shared UUID identity and an internal service token. The Backend is the sole authority for user identity; the Agent is the sole authority for preferences, recommendations, and chat.

```mermaid
sequenceDiagram
    participant U as User
    participant BE as Django Backend
    participant AG as FastAPI Agent

    Note over BE,AG: ── On User Signup ──
    U->>BE: POST /api/signup/ {email, password}
    BE->>BE: Create User, generate auth_token UUID
    BE->>AG: POST /users/{auth_token}\nHeaders: X-Service-Token: <token>\nBody: {email}
    AG->>AG: INSERT user with uid=auth_token, preferences={}, allergies={}
    AG-->>BE: 201 {uid, created: true}
    BE-->>U: {message: "Signup successful. Verify email."}

    Note over BE,AG: ── On Login ──
    U->>BE: POST /api/login/ {email, password}
    BE-->>U: {auth_id: "<auth_token_uuid>"}
    Note over U: Frontend stores auth_id and sends it as X-User-ID on all Agent calls

    Note over BE,AG: ── Allergy Update ──
    U->>BE: PATCH /api/users/{uid}/allergies/ {confirmed: ["peanut"], severity: {...}}
    BE->>AG: PATCH /users/{uid}/allergies\nHeader: X-Service-Token
    AG->>AG: Update allergy_flags, rebuild safety index
    AG-->>BE: 200 OK

    Note over BE,AG: ── On Account Deletion ──
    U->>BE: DELETE /api/users/{uid}/
    BE->>AG: DELETE /users/{uid}\nHeader: X-Service-Token
    AG->>AG: CASCADE DELETE user + interactions
    AG-->>BE: 204 No Content
```

**Key security properties of this integration:**

- The `SERVICE_TOKEN` is a shared secret that must be rotated periodically and never exposed to the Frontend.
- The Agent trusts the `X-User-ID` header without JWT verification — authN is the Backend's responsibility.
- Allergy data is **never** inferred from chat by the profiler; it can only be set by the Backend via `PATCH /users/{uid}/allergies`.
- The `auth_token` field in Django's `User` model is the canonical UID used across all three modules.

For the complete integration reference including all endpoint signatures and error handling, see [Backend/AGENT_INTEGRATION_REPORT.md](Backend/AGENT_INTEGRATION_REPORT.md).

---

## 📦 Deployment

```mermaid
flowchart TD
    A["Developer pushes to main"] --> B["Build Docker image\ndocker build -t kairos-agent ."]
    B --> C["Start database container\ndocker compose up -d db"]
    C --> D{"DB healthy?"}
    D -- No --> E["Wait & retry\n(healthcheck: pg_isready)"]
    E --> D
    D -- Yes --> F["Run Agent\n./run.sh or gunicorn app.main:app"]
    F --> G["Run Django Backend\npython manage.py runserver"]
    G --> H["Run Frontend\nnpm run dev (dev)\nnpm run build + serve (prod)"]
    H --> I["Verify probes\ncurl /health\ncurl /ready"]
```

**Deployment Checklist**

1. Set `APP_ENV=production` to disable SQL echo and hot-reload.
2. Set unique, strong values for `SERVICE_TOKEN`, `DATABASE_URL`, and Django's `SECRET_KEY`.
3. Configure `ALLOWED_ORIGINS` to include only your production domain(s).
4. Replace Django's `DEBUG = True` with `DEBUG = False` and configure `ALLOWED_HOSTS`.
5. Replace Django's plaintext password storage with `make_password` / `check_password` before going live.
6. Run `python scripts/ingest.py --csv data/zomato.csv` to populate the restaurant database.
7. Set up a production WSGI/ASGI server (Gunicorn + Nginx) for both Django and FastAPI.
8. Configure SMTP credentials in Django settings for transactional email.

---

## 🤝 Contributing

All contributions go through pull requests against the `main` branch. Follow the git workflow below to keep the history clean and reviewable.

```mermaid
gitGraph
    commit id: "initial setup"
    branch feature/agent-recommendation
    checkout feature/agent-recommendation
    commit id: "add FitScorer"
    commit id: "add RecommendationService"
    checkout main
    merge feature/agent-recommendation id: "merge: recommendation system"
    branch fix/allergy-guard-severity
    checkout fix/allergy-guard-severity
    commit id: "fix severity ranking"
    checkout main
    merge fix/allergy-guard-severity id: "merge: allergy guard fix"
    branch feature/frontend-map-view
    checkout feature/frontend-map-view
    commit id: "add MapView component"
    checkout main
    merge feature/frontend-map-view id: "merge: map view"
```

**Branch naming convention:**

| Type | Pattern | Example |
|------|---------|---------|
| New feature | `feature/<short-desc>` | `feature/recommendation-cache` |
| Bug fix | `fix/<short-desc>` | `fix/allergen-synonym-lookup` |
| Documentation | `docs/<short-desc>` | `docs/agent-readme` |
| Chore / refactor | `chore/<short-desc>` | `chore/upgrade-fastapi` |

**Pull request checklist:**

- All tests pass (`pytest` for Agent, `manage.py test` for Backend, `npm run lint` for Frontend)
- No `.env` files, API keys, or secrets committed
- Allergy-related changes include a test case for the allergen safety path
- The PR description references the relevant issue number

---

## 📄 License

This project is built for the KSUM Agentic Hackathon by Team Kairos. All rights reserved by the respective contributors. Contact the team lead at me@gokulp.in for licensing inquiries.
