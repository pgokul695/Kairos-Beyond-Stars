# Kairos Agent

The **Agent** module of the Kairos dining concierge platform — the AI reasoning core responsible for restaurant intelligence, personalisation, and allergy safety.

- **Domain**: `kairos-t1.gokulp.online`
- **Stack**: FastAPI · SQLAlchemy (async) · PostgreSQL + pgvector · Google Gemma · Google Embeddings

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- Python 3.11+
- A Google AI API key

### 2. Environment

```bash
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY and SERVICE_TOKEN
```

### 3. Start the Database

```bash
docker-compose up -d
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Create Database Tables

```bash
python scripts/create_tables.py
```

### 6. Ingest Zomato Data

Download the [Zomato Bangalore dataset](https://www.kaggle.com/datasets/himanshupoddar/zomato-bangalore-restaurants/data) and place it at `data/zomato.csv`.

```bash
python scripts/ingest.py --csv data/zomato.csv
# Dry run: python scripts/ingest.py --csv data/zomato.csv --dry-run
# Re-embed only: python scripts/ingest.py --csv data/zomato.csv --re-embed
# Re-tag allergens: python scripts/ingest.py --csv data/zomato.csv --retag-allergens
```

### 7. Run the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Architecture

See [docs/BACKEND_INTEGRATION_REPORT.md](docs/BACKEND_INTEGRATION_REPORT.md) for the complete integration contract.

---

## Key Design Decisions

- **Allergies are never inferred from chat** — only set via `PATCH /users/{uid}/allergies`
- **AllergyGuard is mandatory** — every restaurant result passes through it before returning to the user
- **Anaphylactic + high-confidence matches** are moved to `flagged_restaurants` in the payload
- **Backend owns authentication** — the Agent only trusts `X-Service-Token` for management routes and `X-User-ID` for chat
