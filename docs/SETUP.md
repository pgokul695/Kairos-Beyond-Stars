# Setup Guide — Kairos · Beyond Stars

This guide walks through every step required to run the full Kairos Beyond Stars platform locally, from installing prerequisites to verifying a working end-to-end system. Follow the numbered steps in order for the smoothest experience.

---

## 📋 Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Environment Variables — .env.example Explained](#2-environment-variables--envexample-explained)
3. [Step-by-Step Local Setup](#3-step-by-step-local-setup)
4. [Docker Compose Walkthrough](#4-docker-compose-walkthrough)
5. [run.sh and run_ingest.sh Explained](#5-runsh-and-run_ingestsh-explained)
6. [Common Setup Errors and Fixes](#6-common-setup-errors-and-fixes)
7. [Environment Verification Checklist](#7-environment-verification-checklist)
8. [Related Documents](#related-documents)

---

## 1. Prerequisites

Install the following tools before beginning setup. The table below lists the exact version constraints inferred from each module's configuration.

| Tool | Minimum Version | Required By | Notes |
|------|----------------|-------------|-------|
| Python | 3.11 | Agent, Backend | Agent uses `asyncio.TaskGroup` (3.11+) |
| pip | 23+ | Agent, Backend | Needed for editable installs |
| Node.js | 20 LTS | Frontend | Vite 7 requires Node ≥ 18; 20 LTS recommended |
| npm | 9+ | Frontend | Bundled with Node.js 20 |
| Docker | 20.10+ | Agent (DB) | Needed to run the pgvector container |
| Docker Compose | v2.x (`compose` plugin) | Agent (DB) | Uses `docker compose` (no hyphen) syntax |
| Git | any recent | All | For cloning the repository |
| Google AI Studio account | — | Agent | For `GOOGLE_API_KEY` |
| curl or Httpie | any | All | For verifying API endpoints |

> 💡 **Tip:** On Ubuntu/Debian, install Docker Compose v2 with `sudo apt-get install docker-compose-plugin`. On macOS, Docker Desktop bundles both Docker and Compose v2.

---

## 2. Environment Variables — .env.example Explained

The `.env.example` file at the repository root documents every environment variable used across all three modules. Copy it and fill in your real values before starting any service.

```bash
cp .env.example Agent/.env
# Then edit Agent/.env with your credentials
```

The complete variable reference is listed below. Variables marked **Required** (✅) will cause immediate startup failure if missing.

### Agent Variables

| Variable | Required | Default | Line-by-Line Explanation |
|----------|----------|---------|--------------------------|
| `DATABASE_URL` | ✅ | — | Full async SQLAlchemy connection string. Must use the `postgresql+asyncpg` scheme. Example: `postgresql+asyncpg://kairos:password@localhost:5432/vectordb`. The host must match the Docker container's exposed port. |
| `GOOGLE_API_KEY` | ✅ | — | API key from [Google AI Studio](https://aistudio.google.com/app/apikey). Used for both Gemma-2 inference and text-embedding-004 embeddings. Both models are accessed through the same key. |
| `GEMMA_MODEL` | ❌ | `gemma-2-9b-it` | The Google GenAI model ID for natural language generation. Changing to `gemma-2-27b-it` increases quality but doubles latency and API cost. |
| `EMBEDDING_MODEL` | ❌ | `text-embedding-004` | The Google GenAI model ID for text embeddings. Must produce vectors of `EMBEDDING_DIMENSIONS` dimensions. |
| `EMBEDDING_DIMENSIONS` | ❌ | `768` | Dimensionality of embedding vectors. Must match the `Vector(n)` column definition in the database. **Warning:** Changing this after ingestion requires truncating `reviews` and re-running the full ingest pipeline. |
| `SERVICE_TOKEN` | ✅ | — | A strong random secret shared between the Backend and Agent for inter-service calls. The Backend sends this value as the `X-Service-Token` header. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ALLOWED_ORIGINS` | ❌ | `https://kairos.gokulp.online,http://localhost:3000` | Comma-separated list of CORS origins that the Agent accepts requests from. Must include the Frontend dev server (`http://localhost:5173` for Vite default port) during local development. |
| `APP_ENV` | ❌ | `development` | Affects SQL echo logging and hot-reload. Set to `production` before deploying live. |
| `LOG_LEVEL` | ❌ | `INFO` | Python `logging` module level. Use `DEBUG` during development to see full SQL queries and embedding API calls. |

### Docker / PostgreSQL Variables

| Variable | Required | Default | Explanation |
|----------|----------|---------|-------------|
| `POSTGRES_DB` | ✅ | — | Database name. Must match the database in `DATABASE_URL`. |
| `POSTGRES_USER` | ✅ | — | Database superuser. Must match the user in `DATABASE_URL`. |
| `POSTGRES_PASSWORD` | ✅ | — | Database password. Must match the password in `DATABASE_URL`. |
| `POSTGRES_PORT` | ❌ | `5432` | Host port to expose PostgreSQL on. Change to `5433` if port 5432 is already in use. |

### Backend / Django Variables

| Variable | Required | Default | Explanation |
|----------|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | ✅ | — | Django cryptographic secret. Must be unique per deployment. Generate with `django.core.management.utils.get_random_secret_key()`. |
| `DJANGO_DEBUG` | ❌ | `True` | Set to `False` in production. When `True`, Django returns full tracebacks in HTTP error responses. |
| `AGENT_BASE_URL` | ✅ | `http://localhost:4021` | Base URL the Backend uses to reach the Agent service API. Change to the Agent's production URL when deploying. |
| `AGENT_SERVICE_TOKEN` | ✅ | — | Must exactly match `SERVICE_TOKEN` in the Agent. The Backend sends this as `X-Service-Token` on every call to the Agent. |
| `EMAIL_HOST` | ❌ | — | SMTP host for sending verification emails. |
| `EMAIL_PORT` | ❌ | `2525` | SMTP port. 2525 is used in development; change to 587 (STARTTLS) or 465 (SSL) in production. |
| `EMAIL_HOST_USER` | ❌ | — | SMTP authentication username. |
| `EMAIL_HOST_PASSWORD` | ❌ | — | SMTP authentication password. |
| `DEFAULT_FROM_EMAIL` | ❌ | — | The `From:` address on outgoing emails. |

> ⚠️ **Warning:** Never commit your `.env` file to version control. The repository contains a `.gitignore` that excludes `.env` files, but always verify before committing with `git status`.

---

## 3. Step-by-Step Local Setup

Follow these steps in order. Each step includes a verification command so you can confirm success before proceeding.

### Step 1 — Clone the Repository

```bash
git clone https://github.com/your-org/Kairos-Beyond-Stars.git
cd Kairos-Beyond-Stars
```

**Verify:** `ls` shows `Agent/`, `Backend/`, `Frontend/`, `README.md`

### Step 2 — Create the Agent Environment File

```bash
cp .env.example Agent/.env
```

Open `Agent/.env` and fill in at minimum: `DATABASE_URL`, `GOOGLE_API_KEY`, `SERVICE_TOKEN`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`.

### Step 3 — Start the PostgreSQL Container

```bash
cd Agent
docker compose up -d
```

This starts the `pgvector/pgvector:pg16` container with the settings from `Agent/.env`.

**Verify:**

```bash
docker compose ps
# "kairos_agent_db" (or similar) should show status "healthy"

docker compose exec db psql -U kairos -d vectordb -c "SELECT version();"
# Should print PostgreSQL 16.x
```

> ⚠️ **Warning:** If `docker compose ps` shows the container as `unhealthy`, check credential mismatch between `DATABASE_URL` and `POSTGRES_USER`/`POSTGRES_PASSWORD`.

### Step 4 — Set Up the Agent Python Environment

```bash
# Still in Agent/
./run.sh
```

This script will:
1. Create `Agent/.venv` if it does not exist
2. Install all packages from `requirements.txt`
3. Start the Uvicorn server

When you see `Application startup complete.` in the terminal output, the Agent is running.

**Verify:**

```bash
curl http://localhost:4021/health
# {"status": "healthy"}

curl http://localhost:4021/ready
# {"status": "ready", "database": "ok", "embedding_api": "ok"}
```

### Step 5 — Ingest the Restaurant Dataset

The database starts empty. Ingest data before the Agent can return any results.

```bash
# Download the dataset from Kaggle:
# https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants
# Save to: Agent/data/zomato.csv

cd Agent

# Dry run (no DB writes) — verify parsing first
./run_ingest.sh --dry-run

# Full ingestion
./run_ingest.sh --csv data/zomato.csv

# Full ingestion with embedding generation (slow — one Google API call per review batch)
./run_ingest.sh --csv data/zomato.csv --re-embed
```

> ⚠️ **Warning:** Embedding generation calls the Google AI API for every batch of 100 reviews. For a large CSV this can take significant time and incur API costs. Start with a small subset of the CSV for local development.

### Step 6 — Set Up the Backend

```bash
cd ../Backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install django djangorestframework

# Apply database migrations
python manage.py migrate

# (Optional) Create a Django superuser for /admin/
python manage.py createsuperuser

# Start the development server
python manage.py runserver 8000
```

**Verify:**

```bash
curl -X POST http://localhost:8000/api/signup/ \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"testpass"}'
# {"message": "Signup successful. Please verify your email."}
```

### Step 7 — Set Up the Frontend

```bash
cd ../Frontend/beyond-stars

npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173` (default Vite port) or `http://localhost:3000` depending on `vite.config.js`.

**Verify:** Open the URL in a browser. The hero landing page with the Beyond Stars branding should appear.

---

## 4. Docker Compose Walkthrough

The `Agent/docker-compose.yml` file provisions the PostgreSQL + pgvector database. Here is each block explained:

```yaml
version: '3.9'
# Docker Compose file format version — 3.9 supports the healthcheck syntax below.

services:
  db:
    image: pgvector/pgvector:pg16
    # Official pgvector Docker image bundled with PostgreSQL 16.
    # This image has the vector extension pre-built and auto-loaded.

    container_name: kairos_agent_db
    # Fixed container name for predictable referencing in scripts.

    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    # Docker Compose reads these from Agent/.env automatically
    # when started from the Agent/ directory.

    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    # Maps the container's internal 5432 port to the host.
    # Override POSTGRES_PORT in .env if 5432 is already in use.

    volumes:
      - pgdata:/var/lib/postgresql/data
    # Named volume for persistent storage.
    # Data survives container restarts and rebuilds.

    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
    # pg_isready checks that the Postgres server accepts connections.
    # The Agent runs init_pgvector() only after this healthcheck passes.

volumes:
  pgdata:
    # Named volume definition. Exists at Docker's managed storage path.
    # Remove with: docker compose down -v  (WARNING: destroys all data)
```

> ⚠️ **Warning:** `docker compose down -v` deletes the `pgdata` volume and all restaurant data. You will need to re-run the ingest script to restore data.

---

## 5. run.sh and run_ingest.sh Explained

### `run.sh` — Agent Development Server

```bash
#!/usr/bin/env bash
set -e                          # Exit immediately on any error

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Resolve the absolute path of the Agent/ directory regardless
# of where the script is invoked from.

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtualenv..."
  python3 -m venv "$VENV_DIR"   # Only creates if .venv doesn't exist yet.
fi

source "$VENV_DIR/bin/activate"  # Activate the virtualenv for this shell.

pip install --upgrade pip -q     # Ensure pip is up to date.
pip install -r "$SCRIPT_DIR/requirements.txt" -q
# Install/upgrade all Agent dependencies from requirements.txt.

# Export all variables from .env into the current shell environment.
# Lines starting with # are ignored; blank lines are ignored.
export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)

HOST="${HOST:-0.0.0.0}"          # Default to all interfaces.
PORT="${PORT:-4021}"             # Default to port 4021.
WORKERS="${WORKERS:-1}"          # Default to 1 worker (dev mode).

if [ "$APP_ENV" = "production" ]; then
  # Production: use Gunicorn with multiple sync workers + Uvicorn worker class
  exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "$WORKERS" \
    --bind "$HOST:$PORT"
else
  # Development: use Uvicorn directly with hot-reload
  exec uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload
fi
```

### `run_ingest.sh` — Dataset Ingestion

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Reuse the same virtualenv as run.sh — no extra installation needed
# if run.sh has been executed first.
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

# Export .env variables so the ingest script can reach the database.
export $(grep -v '^#' "$SCRIPT_DIR/.env" | grep -v '^$' | xargs)

# Pass all command-line arguments directly to the ingest script.
# Examples:
#   ./run_ingest.sh --csv data/zomato.csv
#   ./run_ingest.sh --csv data/zomato.csv --dry-run
#   ./run_ingest.sh --csv data/zomato.csv --re-embed --retag-allergens
python "$SCRIPT_DIR/scripts/ingest.py" "$@"
```

---

## 6. Common Setup Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `connection refused` on Agent startup | PostgreSQL container not running | Run `docker compose up -d` in `Agent/`, wait for `healthy` status |
| `FATAL: password authentication failed` | `.env` credentials don't match container | Ensure `POSTGRES_USER`/`POSTGRES_PASSWORD` in `.env` match the Docker container's environment |
| `module 'google.generativeai' has no attribute 'embed_content'` | Wrong `google-generativeai` version | Run `pip install 'google-generativeai>=0.5.0'` |
| `sqlalchemy.exc.ProgrammingError: type "vector" does not exist` | pgvector extension not loaded | The Agent calls `init_pgvector()` on startup; ensure the DB container uses the `pgvector/pgvector:pg16` image, not plain `postgres:16` |
| `422 Unprocessable Entity` on `/chat` | Missing `X-User-ID` header | Add `X-User-ID: <your-uuid>` to the request |
| `403 Forbidden` on `/users/` endpoints | Missing or wrong `X-Service-Token` | Set `SERVICE_TOKEN` in Agent `.env` and send matching value in `X-Service-Token` header |
| Django `No module named 'rest_framework'` | Missing DRF install | `pip install djangorestframework` |
| `vite: command not found` in Frontend | `npm install` not run | Run `npm install` in `Frontend/beyond-stars/` |
| Port 5432 already in use | Local PostgreSQL running | Stop local Postgres or change `POSTGRES_PORT=5433` in `.env` and `DATABASE_URL` accordingly |
| `OSError: [Errno 98] Address already in use` on Agent port 4021 | Another process using 4021 | Change `PORT=4022` or kill the process: `lsof -ti:4021 \| xargs kill` |
| `embed_single returns None` | Invalid or missing `GOOGLE_API_KEY` | Verify the key at [Google AI Studio](https://aistudio.google.com/) and that the `text-embedding-004` model is enabled |

---

## 7. Environment Verification Checklist

Run through this checklist after completing the setup steps to confirm everything is working end-to-end.

### Infrastructure

- [ ] `docker compose ps` shows the database container as `healthy`
- [ ] `psql` connection succeeds: `docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "\dt"` lists the `users`, `restaurants`, `reviews`, `interactions` tables

### Agent

- [ ] `curl http://localhost:4021/health` returns `{"status":"healthy"}`
- [ ] `curl http://localhost:4021/ready` returns `{"status":"ready","database":"ok","embedding_api":"ok"}`
- [ ] Agent logs show no `ERROR` entries on startup

### Backend

- [ ] `curl http://localhost:8000/api/signup/ -d '{"username":"x","email":"x@x.com","password":"x"}' -H "Content-Type: application/json"` returns a success message
- [ ] `curl http://localhost:8000/api/login/ -d '{"email":"x@x.com","password":"x"}' -H "Content-Type: application/json"` returns an `auth_id` UUID after verification

### Frontend

- [ ] `http://localhost:5173` (or `:3000`) loads the hero landing page in the browser
- [ ] The "Start Exploring" button navigates to the `/results` page
- [ ] Restaurant cards render with match scores and images

### End-to-End

- [ ] POST to `/chat` with an `X-User-ID` matching a valid user UUID returns an SSE `result` event
- [ ] The result payload contains a `restaurants` array with at least one entry
- [ ] `AllergyGuard` warnings are present in the response for users who have allergens configured

---

## Related Documents

- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — System architecture overview
- [docs/API.md](API.md) — Full API reference
- [docs/DEPLOYMENT.md](DEPLOYMENT.md) — Production deployment guide
- [Agent/docs/SETUP.md](../Agent/docs/SETUP.md) — Agent-specific setup detail
- [Backend/docs/SETUP.md](../Backend/docs/SETUP.md) — Backend-specific setup detail
- [Frontend/docs/SETUP.md](../Frontend/docs/SETUP.md) — Frontend-specific setup detail
