# Kairos Agent — Backend Integration Report

**Version:** 1.0.0  
**Domain:** `kairos-t1.gokulp.online`  
**Audience:** Backend developers integrating with the Kairos Agent module  
**Last Updated:** 2026-02-27

---

## Table of Contents

1. [Overview](#1-overview)
2. [Authentication Contract](#2-authentication-contract)
3. [Full API Reference](#3-full-api-reference)
4. [Allergy System](#4-allergy-system)
5. [Generative UI Payload Schemas](#5-generative-ui-payload-schemas)
6. [Integration Flows](#6-integration-flows)
7. [Error Codes](#7-error-codes)
8. [Data Boundary](#8-data-boundary)
9. [Deployment & Ops](#9-deployment--ops)

---

## 1. Overview

### What the Agent Module Does

The Agent is the AI reasoning core of the Kairos dining concierge platform. It is responsible for:

- **Restaurant intelligence** — ingesting, embedding, and semantically searching the Zomato Bangalore dataset.
- **Personalisation** — maintaining each user's preference profile, updated from chat signals by a background profiler.
- **Allergy safety** — running every restaurant result through a mandatory safety layer (AllergyGuard) before it is returned to the user.
- **Generative UI** — returning structured JSON payloads that the Frontend renders directly as React components (no template strings, no raw HTML).

The Agent **does not** do authentication, session management, password hashing, or JWT verification. These are entirely the Backend's responsibility. The Agent trusts the `uid` passed to it by the Backend.

### Platform Module Map

| Module    | Domain                        | Owns                                                         |
|-----------|-------------------------------|--------------------------------------------------------------|
| Frontend  | kairos.gokulp.online          | Next.js UI, Vercel AI SDK, Generative UI rendering           |
| Backend   | kariosb.gokulp.online         | Auth, JWT issuance, user registration, sessions              |
| Mail      | kairos-t0.gokulp.online       | Transactional email                                          |
| **Agent** | **kairos-t1.gokulp.online**   | **Restaurant intelligence, personalisation, allergy safety** |

### How `uid` Flows

The Backend is the sole issuer of `uid` values. The flow is:

1. User registers → Backend creates a user record and assigns a UUID v4 `uid`.
2. Backend calls `POST /users/{uid}` on the Agent to initialise the Agent-side profile.
3. All subsequent Agent calls reference this `uid`.
4. The Agent never generates, validates, or modifies `uid` values.

### ASCII Architecture Diagram

```
  User (browser)
       │
       ▼
  ┌─────────────────────┐
  │  Frontend            │   kairos.gokulp.online
  │  Next.js / Vercel    │
  └─────────┬───────────┘
            │ POST /chat
            │ Header: X-User-ID: <uid>
            ▼
  ┌─────────────────────────────────────────────────┐
  │  Agent (kairos-t1.gokulp.online)                │
  │                                                 │
  │  ┌──────────────┐   ┌──────────────────────┐   │
  │  │  Orchestrator │──▶│  Gemma (Google AI)   │   │
  │  └──────┬───────┘   └──────────────────────┘   │
  │         │                                       │
  │  ┌──────▼───────┐   ┌──────────────────────┐   │
  │  │ Hybrid Search │   │  AllergyGuard        │   │
  │  └──────┬───────┘   └──────────────────────┘   │
  │         │                                       │
  │  ┌──────▼───────────────────────────────────┐  │
  │  │  PostgreSQL + pgvector                   │  │
  │  │  restaurants / reviews / users / ...     │  │
  │  └──────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────┘
            ▲
            │ POST /users/{uid}
            │ PATCH /users/{uid}/allergies
            │ DELETE /users/{uid}
            │ Header: X-Service-Token
  ┌─────────┴───────────┐
  │  Backend             │   kariosb.gokulp.online
  │  Auth / Sessions     │
  └─────────────────────┘
```

---

## 2. Authentication Contract

The Agent uses **two separate authentication mechanisms** depending on the caller:

### 2.1 Inter-Service Authentication (Backend → Agent)

Used for all user management endpoints.

| Header           | Value                              | Required |
|------------------|------------------------------------|----------|
| `X-Service-Token`| Shared secret (see `SERVICE_TOKEN` env var) | Yes |

- The Agent compares the header value against its configured `SERVICE_TOKEN`.
- If it does not match, the Agent returns `401 Unauthorized`.
- This token should be a long random string (min 32 characters) stored in the Backend's environment variables.
- **Never put this token in frontend code or URLs.**

### 2.2 User-Delegated Authentication (Frontend → Agent)

Used for the chat endpoint only.

| Header      | Value                         | Required |
|-------------|-------------------------------|----------|
| `X-User-ID` | UUID v4 string of the user    | Yes       |

- The Frontend extracts the `uid` from its session/JWT and forwards it.
- The Agent trusts this value — it does **not** verify JWTs.
- JWT verification is the Backend's responsibility before issuing a session to the Frontend.

### 2.3 Security Recommendations

1. Rotate `SERVICE_TOKEN` at least every 90 days; update both Backend and Agent env simultaneously.
2. Keep the Agent's management endpoints (`/users/*`) firewalled from the public internet; only the Backend's IP range should reach them.
3. The `X-User-ID` path is safe to expose because the Agent never acts on a `uid` that hasn't been previously registered via `POST /users/{uid}` — unknown UIDs return 404.
4. Use HTTPS exclusively in production (both domains already enforce TLS).

---

## 3. Full API Reference

**Base URL (production):** `https://kairos-t1.gokulp.online`

All error responses follow this shape:

```json
{"detail": "Human-readable message", "code": "MACHINE_READABLE_CODE"}
```

---

### 3.1 Health Endpoints

#### `GET /health`

Liveness probe.

**Headers:** None required  
**Response 200:**
```json
{"status": "ok", "version": "1.0.0"}
```

---

#### `GET /ready`

Readiness probe — checks database and embedding API.

**Headers:** None required

**Response 200** (fully ready):
```json
{"db": "ok", "embedding_api": "ok"}
```

**Response 503** (one or more components unavailable):
```json
{"db": "ok", "embedding_api": "error"}
```

---

### 3.2 User Management Endpoints

All user management endpoints require `X-Service-Token`.

---

#### `POST /users/{uid}`

Create a new Agent-side user profile. Idempotent — safe to call multiple times.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |
| `Content-Type`   | `application/json` |

**Path parameters:**

| Parameter | Type   | Description              |
|-----------|--------|--------------------------|
| `uid`     | UUID v4 | The user's stable identifier |

**Request body:**

| Field                  | Type            | Required | Description |
|------------------------|-----------------|----------|-------------|
| `preferences`          | object          | No       | Initial preference snapshot (see shape below) |
| `allergies`            | object          | No       | Initial allergy profile |
| `dietary_flags`        | string[]        | No       | Flat list for fast filtering, e.g. `["vegan"]` |
| `vibe_tags`            | string[]        | No       | Flat list, e.g. `["quiet", "romantic"]` |
| `allergy_flags`        | string[]        | No       | Flat canonical allergen list, e.g. `["peanuts"]`; auto-derived from `allergies` if omitted |
| `preferred_price_tiers`| string[]        | No       | e.g. `["$$", "$$$"]` |

Example request body:
```json
{
  "preferences": {
    "dietary": ["vegan"],
    "vibes": ["quiet", "romantic"],
    "price_comfort": ["$$", "$$$"]
  },
  "allergies": {
    "confirmed": ["peanuts"],
    "intolerances": ["lactose"],
    "severity": {"peanuts": "anaphylactic"}
  },
  "dietary_flags": ["vegan"],
  "vibe_tags": ["quiet", "romantic"],
  "allergy_flags": ["peanuts", "lactose"]
}
```

**Responses:**

| Status | Body                                  | When                  |
|--------|---------------------------------------|-----------------------|
| 201    | `{"uid": "...", "created": true}`     | New user created      |
| 200    | `{"uid": "...", "created": false}`    | User already existed  |
| 401    | Error object                          | Invalid service token |
| 422    | Validation error                      | Invalid request body  |

---

#### `GET /users/{uid}`

Retrieve the full Agent-side user profile.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |

**Response 200:**
```json
{
  "uid": "550e8400-e29b-41d4-a716-446655440000",
  "preferences": {
    "dietary": ["vegan"],
    "vibes": ["quiet", "romantic"],
    "cuisine_affinity": ["south indian"],
    "price_comfort": ["$$", "$$$"],
    "location_bias": {"area": "Koramangala", "radius_km": 5}
  },
  "allergies": {
    "confirmed": ["peanuts"],
    "intolerances": ["lactose"],
    "severity": {"peanuts": "anaphylactic", "lactose": "intolerance"}
  },
  "allergy_flags": ["peanuts", "lactose"],
  "dietary_flags": ["vegan"],
  "vibe_tags": ["quiet", "romantic"],
  "preferred_price_tiers": ["$$", "$$$"],
  "interaction_count": 12,
  "last_active_at": "2026-02-27T10:30:00Z",
  "created_at": "2026-01-15T09:00:00Z",
  "updated_at": "2026-02-27T10:30:00Z"
}
```

| Status | When                  |
|--------|-----------------------|
| 200    | User found            |
| 404    | User not found        |
| 401    | Invalid service token |

---

#### `PATCH /users/{uid}`

Deep-merge new preference signals into the user's preferences. Does **not** touch allergies.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |
| `Content-Type`   | `application/json` |

**Request body:**

| Field         | Type   | Required | Description                    |
|---------------|--------|----------|--------------------------------|
| `preferences` | object | Yes      | Fields to merge into existing preferences |

Example:
```json
{"preferences": {"vibes": ["outdoor"], "price_comfort": ["$$$"]}}
```

**Response 200:**
```json
{"uid": "550e8400-e29b-41d4-a716-446655440000", "updated": true}
```

| Status | When |
|--------|------|
| 200    | Updated successfully |
| 404    | User not found |
| 401    | Invalid service token |

---

#### `PATCH /users/{uid}/allergies`

**Full replace** of the user's allergy profile. This is not a merge — the entire allergies object is replaced.

> **Why full replace?** Allergy data is safety-critical. A merge-based update could leave stale allergens in the profile if the user removes an allergy. Full replace ensures the profile always exactly matches what the user last confirmed.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |
| `Content-Type`   | `application/json` |

**Request body:**

| Field         | Type              | Required | Description |
|---------------|-------------------|----------|-------------|
| `confirmed`   | string[]          | No       | Canonical allergen names the user has confirmed |
| `intolerances`| string[]          | No       | Non-anaphylactic intolerances |
| `severity`    | object            | No       | Map of allergen → severity level |

Severity levels: `"anaphylactic"` | `"severe"` | `"moderate"` | `"intolerance"`

Example:
```json
{
  "confirmed": ["peanuts", "shellfish"],
  "intolerances": ["lactose"],
  "severity": {
    "peanuts": "anaphylactic",
    "shellfish": "severe",
    "lactose": "intolerance"
  }
}
```

**Response 200:**
```json
{
  "uid": "550e8400-e29b-41d4-a716-446655440000",
  "allergy_flags": ["peanuts", "shellfish", "lactose"],
  "updated": true
}
```

The Agent rebuilds `allergy_flags[]` automatically from the new allergies object. The Backend does not need to compute this.

| Status | When |
|--------|------|
| 200    | Updated successfully |
| 404    | User not found |
| 401    | Invalid service token |

---

#### `DELETE /users/{uid}`

Delete a user and all their interaction history.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |

**Responses:**

| Status | When |
|--------|------|
| 204    | Deleted (including cascaded interactions) |
| 404    | User not found |
| 401    | Invalid service token |

---

#### `GET /users/{uid}/interactions`

Retrieve paginated interaction history.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |

**Query parameters:**

| Parameter         | Type    | Default | Description |
|-------------------|---------|---------|-------------|
| `limit`           | integer | 20      | Max 100     |
| `offset`          | integer | 0       |             |
| `include_response`| boolean | false   | Whether to include the full `agent_response` JSON |

**Response 200:**
```json
{
  "interactions": [
    {
      "id": 42,
      "uid": "550e8400-...",
      "user_query": "Find a quiet romantic restaurant",
      "agent_response": {},
      "ui_type": "radar_comparison",
      "restaurant_ids": [101, 205, 88],
      "allergy_warnings_shown": true,
      "allergens_flagged": ["peanuts"],
      "prompt_tokens": 512,
      "completion_tokens": 256,
      "created_at": "2026-02-27T10:30:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

#### `DELETE /users/{uid}/interactions`

Clear all interaction history for a user. Keeps the user record intact.

**Headers:**

| Header           | Required |
|------------------|----------|
| `X-Service-Token`| Yes      |

**Response 204:** No body.

---

### 3.3 Chat Endpoint

#### `POST /chat`

Process a user message and stream the Agent's response.

**Headers:**

| Header        | Required | Description |
|---------------|----------|-------------|
| `X-User-ID`   | Yes      | UUID v4 of the authenticated user |
| `Content-Type`| Yes      | `application/json` |

**Request body:**

| Field                  | Type            | Required | Description |
|------------------------|-----------------|----------|-------------|
| `message`              | string (1–2000) | Yes      | The user's current message |
| `conversation_history` | array           | No       | Recent chat history (last N turns) |

Each element of `conversation_history`:

| Field     | Type   | Values |
|-----------|--------|--------|
| `role`    | string | `"user"` \| `"assistant"` |
| `content` | string | Message text |

Example request:
```json
{
  "message": "Find a quiet romantic restaurant for my anniversary, I'm vegan",
  "conversation_history": [
    {"role": "user", "content": "What areas in Bangalore do you cover?"},
    {"role": "assistant", "content": "I cover all major areas in Bangalore including Koramangala, Indiranagar, HSR Layout, Whitefield, and more!"}
  ]
}
```

**Response:** `Content-Type: text/event-stream`

The response is a Server-Sent Events stream. Each line is a JSON object:

```
{"event": "thinking", "data": {"step": "decomposing_query"}}
{"event": "thinking", "data": {"step": "searching", "filters": {...}}}
{"event": "thinking", "data": {"step": "evaluating", "count": 10}}
{"event": "thinking", "data": {"step": "checking_allergies"}}
{"event": "result",   "data": <GenerativeUIPayload>}
```

`thinking` events are optional UI indicators (loading state). `result` is always the last event and contains the payload the Frontend renders.

---

## 4. Allergy System

### 4.1 Why Allergies Are Separate from Preferences

User preferences (dietary style, vibes, cuisine affinity) are **soft signals** — the Agent infers and updates them from conversation. They may be imprecise; a wrong inference is annoying but not dangerous.

Allergy data is **safety-critical**. An error could cause anaphylaxis. Therefore:

- Allergies live in a separate `allergies` JSONB column, never in `preferences`.
- **Allergies are never inferred from chat.** The background profiler that updates preferences has a hard rule never to return allergy fields.
- Allergies are only updated by `PATCH /users/{uid}/allergies`, which the Backend calls as a result of an explicit, deliberate action by the user in the settings UI.

### 4.2 Severity Levels

| Severity       | Meaning | UI treatment |
|----------------|---------|--------------|
| `anaphylactic` | Life-threatening; epinephrine required | 🚨 Red danger banner; restaurant moved to `flagged_restaurants` if allergen confirmed with high confidence |
| `severe`       | Serious allergic reaction likely      | ⚠️ Warning; restaurant shown in main list with prominent warning |
| `moderate`     | Allergic reaction possible            | ⚡ Caution; restaurant shown with advisory note |
| `intolerance`  | Digestive discomfort, not life-threatening | ℹ️ Info note; restaurant shown normally |

### 4.3 How the Backend Sets Allergies

The Backend should call `PATCH /users/{uid}/allergies` whenever:

- The user explicitly adds or removes an allergen in the profile/settings UI.
- The user changes a severity level.
- The user clears their allergy profile.

Because this is a **full replace**, the Backend must always send the complete current allergy state, not just the changed fields.

**Example flow:**

1. User has peanuts (anaphylactic) on file.
2. User adds shellfish (severe) in settings.
3. Backend calls: `PATCH /users/{uid}/allergies` with `{"confirmed": ["peanuts", "shellfish"], "intolerances": [], "severity": {"peanuts": "anaphylactic", "shellfish": "severe"}}`.
4. Agent replaces the allergies object and rebuilds `allergy_flags = ["peanuts", "shellfish"]`.

### 4.4 AllergyGuard Runtime Behaviour

Every chat response passes restaurants through the AllergyGuard before any data leaves the Agent:

1. **Hard SQL filter** (Step 3 of orchestrator): any allergen marked `anaphylactic` is excluded at the database query level. This is a hard filter — anaphylactic restaurants never appear in results at all, **unless** allergen confidence is `medium` or `low` (data from heuristics, not confirmed text), in which case they proceed to step 2.
2. **Warning annotation** (Step 5 of orchestrator): for all non-anaphylactic allergens (and anaphylactic allergens with non-high confidence), the AllergyGuard annotates each restaurant with `allergy_warnings` and marks `allergy_safe = true/false`.
3. **Flagged list**: restaurants where an allergen is `anaphylactic` severity **AND** `allergen_confidence = 'high'` are moved to `flagged_restaurants[]` in the payload and rendered with a red danger banner.
4. **Sorting**: safe restaurants appear first; within unsafe restaurants, sorted by worst-case severity (intolerance → moderate → severe → anaphylactic last).
5. **Never silent**: the Agent never hides a restaurant silently because of allergies. It always shows a warning so the user makes an informed decision.

### 4.5 `restaurants` vs `flagged_restaurants` in the Payload

| Field                  | Contains |
|------------------------|-------------------------------------------------------------------------|
| `restaurants`          | All results, including those with warnings (sorted safe-first)          |
| `flagged_restaurants`  | Only results with `anaphylactic` severity + `high` allergen confidence  |
| `has_allergy_warnings` | `true` if any result in either list has warnings                        |

The Frontend should render `flagged_restaurants` in a separate section, clearly labelled as high-risk, distinct from the main restaurant list.

---

## 5. Generative UI Payload Schemas

All payloads share this top-level structure:

```json
{
  "ui_type": "<type>",
  "message": "Natural language message accompanying the results",
  "restaurants": [...],
  "flagged_restaurants": [...],
  "has_allergy_warnings": true
}
```

Every restaurant object in every payload type always includes these allergy fields:

```json
{
  "allergy_safe": false,
  "allergy_warnings": [
    {
      "allergen": "peanuts",
      "severity": "anaphylactic",
      "level": "danger",
      "emoji": "🚨",
      "title": "Anaphylaxis Risk",
      "message": "This restaurant may contain peanuts. Given your severe allergy, we strongly recommend calling ahead to confirm before visiting.",
      "confidence": "high",
      "confidence_note": null
    }
  ]
}
```

When `confidence != "high"`:
```json
{
  "confidence": "medium",
  "confidence_note": "Allergen data for this restaurant is estimated from cuisine type — always confirm with staff before ordering."
}
```

---

### 5.1 `restaurant_list`

A flat list of restaurants. Used for general queries.

```json
{
  "ui_type": "restaurant_list",
  "message": "I found 4 great vegan-friendly restaurants in Koramangala!",
  "has_allergy_warnings": false,
  "restaurants": [
    {
      "id": 101,
      "name": "Green Theory",
      "area": "Koramangala",
      "address": "80 Feet Road, Koramangala 4th Block",
      "price_tier": "$$",
      "rating": 4.3,
      "votes": 1820,
      "cuisine_types": ["continental", "salads", "healthy food"],
      "url": "https://www.zomato.com/green-theory",
      "known_allergens": ["gluten", "dairy"],
      "allergen_confidence": "medium",
      "meta": {"dish_liked": ["avocado toast", "smoothie bowls"]},
      "allergy_safe": true,
      "allergy_warnings": []
    }
  ],
  "flagged_restaurants": []
}
```

---

### 5.2 `radar_comparison`

Used when the user wants to compare restaurants on multiple dimensions (romance, noise, food quality, etc.).

Adds `scores` to each restaurant:

```json
{
  "ui_type": "radar_comparison",
  "message": "Here are 3 romantic options for your anniversary! One has an allergy note — I've flagged it clearly.",
  "has_allergy_warnings": true,
  "restaurants": [
    {
      "id": 205,
      "name": "The Fatty Bao",
      "area": "Indiranagar",
      "price_tier": "$$$",
      "rating": 4.5,
      "votes": 3200,
      "cuisine_types": ["asian", "japanese", "thai"],
      "allergy_safe": false,
      "allergy_warnings": [
        {
          "allergen": "soy",
          "severity": "intolerance",
          "level": "info",
          "emoji": "ℹ️",
          "title": "Note",
          "message": "This restaurant serves dishes with soy. Allergen-free options may be available — worth checking with staff.",
          "confidence": "medium",
          "confidence_note": "Allergen data for this restaurant is estimated from cuisine type — always confirm with staff before ordering."
        }
      ],
      "scores": {
        "romance": 8.5,
        "noise_level": 6.0,
        "food_quality": 9.0,
        "vegan_options": 5.5,
        "value_for_money": 7.0
      }
    }
  ],
  "flagged_restaurants": []
}
```

---

### 5.3 `map_view`

Used when the query has a strong location component ("restaurants near me", "within 2 km").

Includes `lat`/`lng` on each restaurant, plus an optional `map_center`:

```json
{
  "ui_type": "map_view",
  "message": "Here are 5 restaurants near Koramangala, sorted by rating.",
  "has_allergy_warnings": false,
  "map_center": {"lat": 12.9352, "lng": 77.6245},
  "restaurants": [
    {
      "id": 88,
      "name": "Meghana Foods",
      "area": "Koramangala",
      "lat": 12.9340,
      "lng": 77.6230,
      "price_tier": "$$",
      "rating": 4.6,
      "cuisine_types": ["biryani", "north indian"],
      "allergy_safe": true,
      "allergy_warnings": []
    }
  ],
  "flagged_restaurants": []
}
```

---

### 5.4 `text`

Used when no restaurants are being recommended — clarifications, general questions, errors.

```json
{
  "ui_type": "text",
  "message": "Could you tell me which area of Bangalore you're looking in? That will help me find the best options for you.",
  "restaurants": [],
  "flagged_restaurants": [],
  "has_allergy_warnings": false,
  "follow_up_questions": [
    "Are you looking in North, South, East, or West Bangalore?",
    "Do you have a specific neighborhood in mind?"
  ]
}
```

---

## 6. Integration Flows

### 6.1 New User Registration

```
1. User completes registration on the Frontend.

2. Backend creates the user record in its own database (generates uid = UUID v4).

3. Backend immediately calls:
   POST https://kairos-t1.gokulp.online/users/{uid}
   Headers: X-Service-Token: <token>
   Body: {
     "preferences": {},
     "allergies": {},
     "dietary_flags": [],
     "vibe_tags": [],
     "allergy_flags": []
   }

4. Agent creates the profile row.
   → 201 {"uid": "...", "created": true}

5. Backend returns the JWT/session to the Frontend.
   The Frontend is now ready to call POST /chat.

   Note: If the Agent is unavailable at step 3, the Backend should retry
   up to 3 times with exponential backoff. Registration is still considered
   successful even if the Agent profile creation fails — it will be created
   lazily on the first GET /users/{uid} call.
```

### 6.2 Chat Turn

```
1. User sends a message on the Frontend.

2. Frontend makes an authenticated request:
   POST https://kairos-t1.gokulp.online/chat
   Headers: X-User-ID: <uid>
   Body: {"message": "...", "conversation_history": [...]}

3. Agent streams SSE:
   → {"event": "thinking", "data": {"step": "decomposing_query"}}
   → {"event": "thinking", "data": {"step": "searching", "filters": {...}}}
   → {"event": "thinking", "data": {"step": "evaluating", "count": 10}}
   → {"event": "thinking", "data": {"step": "checking_allergies"}}
   → {"event": "result",   "data": <GenerativeUIPayload>}

4. Frontend receives "result" event and renders the appropriate React component
   based on ui_type.

5. Background (fire-and-forget in Agent):
   - Interaction record saved to DB.
   - Profiler updates user preferences.
```

### 6.3 Allergy Profile Update

```
1. User opens the allergy settings on the Frontend.

2. User adds "shellfish" (severe) and removes an old allergy.

3. Frontend sends the change to the Backend.

4. Backend validates the input and calls:
   PATCH https://kairos-t1.gokulp.online/users/{uid}/allergies
   Headers: X-Service-Token: <token>
   Body: {
     "confirmed": ["peanuts", "shellfish"],   ← full current state
     "intolerances": ["lactose"],
     "severity": {
       "peanuts":   "anaphylactic",
       "shellfish": "severe",
       "lactose":   "intolerance"
     }
   }

5. Agent performs a FULL REPLACE of the allergies object and rebuilds
   allergy_flags[].
   → 200 {"uid": "...", "allergy_flags": ["peanuts", "shellfish", "lactose"], "updated": true}

6. Backend confirms success to the Frontend.

7. All subsequent chat turns will use the updated allergy profile.
```

### 6.4 Account Deletion

```
1. User requests account deletion.

2. Backend performs its own cleanup (sessions, credentials, etc.).

3. Backend calls:
   DELETE https://kairos-t1.gokulp.online/users/{uid}
   Headers: X-Service-Token: <token>

4. Agent deletes:
   - users row
   - All interactions (CASCADE)

   → 204 No Content

5. Backend confirms deletion to the Frontend and clears the session.
```

---

## 7. Error Codes

| Code                   | HTTP Status | Description |
|------------------------|-------------|-------------|
| `USER_NOT_FOUND`       | 404         | No user with the given uid exists in the Agent database. Backend should call `POST /users/{uid}` first. |
| `INVALID_SERVICE_TOKEN`| 401         | The `X-Service-Token` header is missing or does not match the configured secret. |
| `MISSING_USER_ID`      | 400         | The `X-User-ID` header is missing or is not a valid UUID v4. |
| `AGENT_UNAVAILABLE`    | 500         | Unhandled internal error. The Backend should retry with exponential backoff. |
| `INVALID_PAYLOAD`      | 422         | Request body failed Pydantic validation. The `detail` field will contain field-level error descriptions. |

---

## 8. Data Boundary

The Agent and Backend each own distinct data. Neither should attempt to replicate or override the other's data.

| Field / Data             | Owner   | Who Can Write         | Notes |
|--------------------------|---------|-----------------------|-------|
| `uid`                    | Backend | Backend only          | Agent never generates UIDs |
| `email`, `password_hash` | Backend | Backend only          | Agent never stores credentials |
| `jwt_secret`, sessions   | Backend | Backend only          | Agent has no auth logic |
| `preferences`            | Agent   | Agent (from profiler) + Backend (PATCH /users/{uid}) | Soft preference signals |
| `allergies`              | Agent   | Backend only (`PATCH /users/{uid}/allergies`) | Safety-critical; never inferred from chat |
| `allergy_flags`          | Agent   | Agent (auto-derived from allergies) | Denormalised for fast querying |
| `dietary_flags`          | Agent   | Agent profiler + Backend | Denormalised from preferences |
| `vibe_tags`              | Agent   | Agent profiler + Backend | Denormalised from preferences |
| `interaction_count`      | Agent   | Agent only            | Bumped on every chat turn |
| `last_active_at`         | Agent   | Agent only            | Updated on every chat turn |
| `restaurants`            | Agent   | Agent (ingestion only) | Zomato Bangalore dataset |
| `reviews`/embeddings     | Agent   | Agent (ingestion only) | Vector data for semantic search |

---

## 9. Deployment & Ops

### 9.1 Required Environment Variables

| Variable              | Description                                       | Example |
|-----------------------|---------------------------------------------------|---------|
| `DATABASE_URL`        | Async PostgreSQL connection string                | `postgresql+asyncpg://user:pass@host:5432/db` |
| `GOOGLE_API_KEY`      | Google AI API key for Gemma + Embeddings          | `AIza...` |
| `SERVICE_TOKEN`       | Shared secret for inter-service auth              | 32+ char random string |
| `ALLOWED_ORIGINS`     | Comma-separated CORS origins                      | `https://kairos.gokulp.online,http://localhost:3000` |
| `GEMMA_MODEL`         | Gemma model name                                  | `gemma-2-9b-it` |
| `EMBEDDING_MODEL`     | Google embedding model                            | `text-embedding-004` |
| `EMBEDDING_DIMENSIONS`| Embedding vector size                             | `768` |
| `APP_ENV`             | `development` or `production`                     | `production` |
| `LOG_LEVEL`           | Python logging level                              | `INFO` |

### 9.2 Network Requirements

| Direction           | From         | To                            | Port | Protocol |
|---------------------|--------------|-------------------------------|------|----------|
| User management     | Backend      | `kairos-t1.gokulp.online`     | 443  | HTTPS    |
| Chat                | Frontend     | `kairos-t1.gokulp.online`     | 443  | HTTPS (SSE) |
| DB                  | Agent        | PostgreSQL host               | 5432 | TCP      |
| Google AI           | Agent        | `generativelanguage.googleapis.com` | 443 | HTTPS |

**Firewall recommendation:** The `/users/*` endpoints should not be accessible from the public internet. Place the Agent behind an API gateway or use IP allowlisting to restrict `/users/*` to the Backend's IP range only.

### 9.3 Health Check Endpoints for Monitoring

The Backend's uptime monitoring system should poll these endpoints:

| Endpoint    | Expected Response       | Interval | Alerting threshold |
|-------------|------------------------|----------|--------------------|
| `GET /health` | `200 {"status":"ok"}` | 30s      | 2 consecutive failures |
| `GET /ready`  | `200 {"db":"ok","embedding_api":"ok"}` | 60s | 3 consecutive failures |

If `GET /ready` returns 503, the Agent can still serve cached/degraded results. The Backend should:
- Continue forwarding chat requests (the Agent handles degraded states gracefully).
- Alert on-call if the condition persists for more than 5 minutes.

### 9.4 Recommended Retry Policy (Backend → Agent)

| Scenario                               | Retry strategy |
|----------------------------------------|----------------|
| `POST /users/{uid}` fails at registration | 3 retries, exponential backoff starting at 1 s |
| `PATCH /users/{uid}/allergies` fails   | 3 retries, exponential backoff; alert if all fail (critical safety path) |
| `DELETE /users/{uid}` fails            | 3 retries; schedule a deferred cleanup job on persistent failure |
| `GET /health` / `GET /ready` returns 503 | Retry every 30 s; stop routing to Agent if down for > 5 min |
| `POST /chat` fails (502/503)           | Frontend retries once after 2 s; shows user error on second failure |

For the allergy patch endpoint specifically, persistent failure must trigger an alert because the user's safety profile was not updated. The Backend should log the attempted request and retry it when the Agent recovers.

### 9.5 Starting the Agent

```bash
# 1. Start dependencies
docker-compose up -d

# 2. Create tables (idempotent)
python scripts/create_tables.py

# 3. Ingest Zomato data (one-time)
python scripts/ingest.py --csv data/zomato.csv

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

In production, run with `--workers 4` (or via gunicorn with uvicorn workers):

```bash
gunicorn app.main:app -k uvicorn.workers.UvicornWorker --workers 4 --bind 0.0.0.0:8001
```

---

*This document was generated as part of the Kairos Agent module and covers all information needed for a complete Backend integration. For any questions, consult the Agent README or raise an issue in the repository.*
