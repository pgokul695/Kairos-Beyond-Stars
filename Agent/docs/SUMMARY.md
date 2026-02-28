# Agent Summary — Kairos · Beyond Stars

This document summarises what the Agent module does, its key capabilities, known limitations, and the planned improvement roadmap.

---

## 📋 Table of Contents

1. [What the Agent Does](#1-what-the-agent-does)
2. [Key Capabilities](#2-key-capabilities)
3. [Limitations and Known Issues](#3-limitations-and-known-issues)
4. [Improvement Roadmap](#4-improvement-roadmap)
5. [Related Documents](#related-documents)

---

## 1. What the Agent Does

The Agent is the AI intelligence core of the Kairos Beyond Stars platform. In plain terms: it takes a natural language message from a user ("cheap vegetarian Chinese near Indiranagar, I'm allergic to soy"), figures out what they want, searches the restaurant database using both keyword rules and semantic meaning, ranks the results by how well they match the user's taste profile, checks every result for allergen safety, and streams the answer back to the frontend in real time.

The Agent also maintains a continuously-updated taste profile for each user. After every conversation turn, it silently extracts preference signals (cuisine affinity, vibe preferences, price comfort) from the exchange and updates the user's profile for future queries. This happens in the background without slowing the response.

Beyond the chat experience, the Agent serves a daily personalised recommendation feed — a ranked list of restaurants scored against the user's full taste profile — cached for 24 hours to keep API costs low.

---

## 2. Key Capabilities

| Capability | Technical Implementation |
|-----------|------------------------|
| **Natural language restaurant search** | 5-step ReAct loop: context load → Gemma decomposition → hybrid search → Gemma evaluation → AllergyGuard |
| **Semantic search** | Review text embedded into 768-dim vectors with `text-embedding-004`; stored in PostgreSQL pgvector; queried with `<=>` cosine distance |
| **SQL + vector hybrid search** | `hybrid_search.py` combines `WHERE` clause filters with `ORDER BY embedding <=> :vec` in a single PostgreSQL query |
| **Allergy safety** | `AllergyGuard.check()`: mandatory call on every result path. Checks known_allergens, review mentions, and cuisine-based inference. Severity-ranked, safe-first ordering |
| **Preference learning** | `profiler.py`: fire-and-forget Gemma call after each turn. Allowlist-protected (cannot touch allergy data). Deep-merge strategy for cumulative profile building |
| **Personalised recommendations** | `FitScorer.score()`: 0-100 pure-Python scorer across 5 weighted dimensions. 24-hour TTL cache keyed by `sha256(uid+date)` |
| **Streaming responses** | `POST /chat` returns `text/event-stream` SSE with `thinking` events per step + single `result` event |
| **Generative UI** | `ui_type` field in every result tells Frontend which component to render (list/map/chart/text) |
| **Inter-service security** | `X-Service-Token` header on all Backend → Agent calls; `X-User-ID` for Frontend → Agent calls |
| **Dataset ingestion** | `scripts/ingest.py`: CSV parsing, allergen tagging, batched embeddings, idempotent upsert |

---

## 3. Limitations and Known Issues

| Issue | Severity | Detail |
|-------|----------|--------|
| `recommendations.py` router not registered | High | The router file exists and is fully implemented but is not in the `include_router()` calls in `main.py`. Add `app.include_router(recommendations.router)` to activate. |
| `chroma_client.py` references undefined `settings.chroma_path` | Medium | The file references `settings.chroma_path` which is not declared in `config.py`. This causes a startup error if `chroma_client.py` is imported. Add `chroma_path: str = "chroma_store"` to `Settings`. |
| `local_ml.py` 384-dim vectors incompatible with `Vector(768)` column | Medium | If enabled, the local embedding model produces 384-dimensional vectors that cannot be stored in the `reviews.embedding Vector(768)` column. Requires either a schema migration or a separate column. |
| No test suite in `requirements.txt` | Medium | `pytest`, `pytest-asyncio`, and `httpx` are not in requirements. Tests cannot be run without manually installing these packages. |
| Recommendation cache is in-process only | Low | The `TTLCache` is per-process. Multiple agent replicas each maintain their own cache. This is acceptable for single-host deployments; multi-replica deployments should use Redis. |
| No JWT or cryptographic user verification | Low | The `X-User-ID` header is validated as a UUID format but not cryptographically signed. The Backend is trusted to issue valid UUIDs. For higher security environments, add JWT verification. |
| Embedding `None` silently excluded from search | Info | Reviews that fail embedding are stored with `NULL` embedding and will never appear in vector-similarity searches. They will still appear in SQL-only searches. Monitor the ingest log for embedding failure rates. |

---

## 4. Improvement Roadmap

The following improvements are planned for the Agent module, ordered by priority:

### P0 — Critical (Block deployment)

| Item | Description |
|------|-------------|
| Register `recommendations.py` router | Add `app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])` to `main.py`. |
| Fix `chroma_client.py` settings reference | Add `chroma_path: str = "chroma_store"` to the `Settings` class in `config.py`. |
| Add `pytest` to `requirements.txt` | Add `pytest>=7.0`, `pytest-asyncio>=0.23`, `httpx>=0.27`, `pytest-cov>=4.0`. |

### P1 — High Priority

| Item | Description |
|------|-------------|
| AllergyGuard safety matrix tests | Add parametrized tests covering every `CANONICAL_ALLERGEN` and every severity level. |
| Rate limiting on `/chat` endpoint | Add `slowapi` middleware to limit chat requests per `X-User-ID` (suggested: 20 req/min per user). |
| Chat endpoint authentication improvement | Validate that the `X-User-ID` corresponds to an existing user in the database before starting the orchestration loop. |

### P2 — Medium Priority

| Item | Description |
|------|-------------|
| Redis recommendation cache | Replace `TTLCache` with a Redis-based cache for multi-replica deployments. |
| Structured logging | Replace `print()` debugging with structured JSON logs using `structlog` for production observability. |
| Streaming metrics | Emit a `metrics` SSE event at the end of each chat turn with `input_tokens`, `output_tokens`, `latency_ms`. |
| Multi-language allergen synonyms | Extend `ALLERGEN_SYNONYMS` to cover more regional Indian language food terms. |

### P3 — Nice to Have

| Item | Description |
|------|-------------|
| Self-hosted Gemma | Support `GEMMA_BACKEND=local` that routes to an Ollama or vLLM endpoint instead of the Google AI API. Eliminates Google API dependency and cost. |
| Async recommendation recompute | Trigger a background recommendation recompute when the user's preference profile is significantly updated (cosine similarity delta threshold). |
| Allergen confidence upgrade pipeline | Periodically re-scan new review imports for allergen mentions and upgrade `allergen_confidence` from `medium` to `high` automatically. |

---

## Related Documents

- [Agent/README.md](../README.md) — Agent entry point
- [Agent/docs/ARCHITECTURE.md](ARCHITECTURE.md) — Full pipeline architecture
- [Agent/docs/SETUP.md](SETUP.md) — Setup and dependencies
- [Agent/docs/API.md](API.md) — Service function reference
- [docs/SUMMARY.md](../../docs/SUMMARY.md) — Full project summary
