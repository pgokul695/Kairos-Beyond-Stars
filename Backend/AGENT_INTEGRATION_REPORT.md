# Kairos Agent — Django Backend Integration Report

**Agent URL (production):** `https://kairos-t1.gokulp.online`  
**Agent URL (local dev):** `http://localhost:4021`  
**Backend:** Django 5.2 + Django REST Framework  
**Last Updated:** 2026-02-27

---

## Table of Contents

1. [Overview & UID Mapping](#1-overview--uid-mapping)
2. [Django Settings & Environment](#2-django-settings--environment)
3. [Agent Service Utility](#3-agent-service-utility)
4. [User Registration — Signup Hook](#4-user-registration--signup-hook)
5. [Login — Forwarding the UID to the Frontend](#5-login--forwarding-the-uid-to-the-frontend)
6. [Allergy Management Endpoints](#6-allergy-management-endpoints)
7. [Preference Update Endpoint](#7-preference-update-endpoint)
8. [Account Deletion Hook](#8-account-deletion-hook)
9. [Admin Utilities — Interaction History](#9-admin-utilities--interaction-history)
10. [Error Handling & Retry Policy](#10-error-handling--retry-policy)
11. [Full URL Configuration](#11-full-url-configuration)
12. [End-to-End Flow Diagrams](#12-end-to-end-flow-diagrams)
13. [Security Checklist](#13-security-checklist)

---

## 1. Overview & UID Mapping

### How `auth_token` Becomes `uid`

The current `User` model already has exactly what the Agent needs:

```python
# core/models.py (current)
class User(models.Model):
    auth_token = models.UUIDField(default=uuid.uuid4, editable=False)
```

`auth_token` **is** the Agent's `uid`. Wherever this document or the Agent API says `uid`, you pass `str(user.auth_token)`.

```python
uid = str(user.auth_token)  # e.g. "550e8400-e29b-41d4-a716-446655440000"
```

### Responsibility Split

| Concern | Owner | Notes |
|---|---|---|
| `auth_token` (uid) generation | Django Backend | `uuid.uuid4()` — already in place |
| Email verification | Django Backend | Already implemented |
| Password hashing | Django Backend | **Needs upgrade** — currently stored plain-text (see §2) |
| JWT/session issuance | Django Backend | Backend returns `auth_id` to Frontend |
| Chat | Agent (direct from Frontend) | Frontend sends `X-User-ID: <auth_token>` |
| Allergy profile | Django Backend calls Agent | `PATCH /users/{uid}/allergies` |
| Restaurant search | Agent (direct from Frontend) | Via `POST /chat` |
| Preference learning | Agent (automatic) | Background profiler; no Backend action needed |

### Data Flow

```
  User (browser)
       │
       ├─── POST /api/signup/    ──────────────────────►  Django Backend
       │                                                        │
       │                                              POST /users/{uid}
       │                                                        │
       │                                                        ▼
       │                                               Agent (kairos-t1)
       │
       ├─── POST /api/login/     ──────────────────────►  Django Backend
       │         ◄── { auth_id: "<uid>" }
       │
       └─── POST /chat           ──────────────────────►  Agent (kairos-t1)
                Header: X-User-ID: <auth_id>              (direct, no Backend hop)
```

The Frontend uses `auth_id` (the `auth_token` UUID) both as:
1. The session identifier with the Backend
2. The `X-User-ID` header value with the Agent

---

## 2. Django Settings & Environment

### 2.1 Add Agent Config to `settings.py`

```python
# beyondstars_backend/settings.py

import os

# ── Kairos Agent ──────────────────────────────────────────────────────────────
AGENT_BASE_URL = os.environ.get("AGENT_BASE_URL", "http://localhost:4021")
AGENT_SERVICE_TOKEN = os.environ.get("AGENT_SERVICE_TOKEN", "")
AGENT_TIMEOUT_SECONDS = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "10"))
```

### 2.2 Environment Variables to Add

Create or extend your Backend `.env` file:

```dotenv
# Kairos Agent
AGENT_BASE_URL=https://kairos-t1.gokulp.online
AGENT_SERVICE_TOKEN=strong_random_secret_here   # Must match Agent's SERVICE_TOKEN
AGENT_TIMEOUT_SECONDS=10
```

> **Critical:** `AGENT_SERVICE_TOKEN` must be identical to the `SERVICE_TOKEN` value in the Agent's `.env`. Never commit this value — add `.env` to `.gitignore`.

### 2.3 Password Hashing (Security Fix)

The current code stores passwords in plain text — fix this before production:

```python
# core/models.py — add this method
from django.contrib.auth.hashers import make_password, check_password

class User(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)   # increase length for hashes
    is_verified = models.BooleanField(default=False)
    auth_token = models.UUIDField(default=uuid.uuid4, editable=False)

    def set_password(self, raw_password: str) -> None:
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.email
```

---

## 3. Agent Service Utility

Create a dedicated service module. This centralises all HTTP calls to the Agent so they are easy to test, mock, and retry.

```python
# core/agent_service.py

import logging
import time
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

AGENT_BASE_URL: str = settings.AGENT_BASE_URL.rstrip("/")
SERVICE_TOKEN: str = settings.AGENT_SERVICE_TOKEN
TIMEOUT: int = settings.AGENT_TIMEOUT_SECONDS

_SERVICE_HEADERS = {
    "X-Service-Token": SERVICE_TOKEN,
    "Content-Type": "application/json",
}


def _request_with_retry(
    method: str,
    path: str,
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    **kwargs: Any,
) -> requests.Response:
    """
    Make an HTTP request to the Agent with automatic exponential-backoff retry.

    Retries on connection errors and 5xx responses.
    Raises requests.HTTPError on non-retryable 4xx errors after the first attempt.
    Raises requests.ConnectionError if all retries are exhausted.
    """
    url = f"{AGENT_BASE_URL}{path}"
    backoff = initial_backoff

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=_SERVICE_HEADERS,
                timeout=TIMEOUT,
                **kwargs,
            )

            # 4xx errors (except 404 on DELETE which is acceptable) — don't retry
            if 400 <= response.status_code < 500:
                response.raise_for_status()

            # 5xx — retry
            if response.status_code >= 500:
                raise requests.HTTPError(
                    f"Agent returned {response.status_code}", response=response
                )

            return response

        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == max_retries:
                logger.error(
                    "Agent request failed after %d attempts: %s %s — %s",
                    max_retries, method, path, exc,
                )
                raise
            logger.warning(
                "Agent request attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, max_retries, exc, backoff,
            )
            time.sleep(backoff)
            backoff *= 2

    # unreachable, satisfies type-checker
    raise requests.ConnectionError("Exhausted retries")


# ── User Management ───────────────────────────────────────────────────────────

def create_agent_user(
    uid: str,
    preferences: dict | None = None,
    allergies: dict | None = None,
    dietary_flags: list[str] | None = None,
    vibe_tags: list[str] | None = None,
    allergy_flags: list[str] | None = None,
) -> dict:
    """
    Register a new user with the Agent.
    Idempotent — safe to call multiple times for the same uid.

    Returns:
        {"uid": "...", "created": True}   on first creation
        {"uid": "...", "created": False}  if uid already existed
    """
    payload = {
        "preferences": preferences or {},
        "allergies": allergies or {},
        "dietary_flags": dietary_flags or [],
        "vibe_tags": vibe_tags or [],
        "allergy_flags": allergy_flags or [],
    }
    response = _request_with_retry("POST", f"/users/{uid}", json=payload)
    return response.json()


def get_agent_user(uid: str) -> dict:
    """
    Fetch a user's full Agent-side profile.

    Raises requests.HTTPError (404) if the user does not exist in the Agent.
    """
    response = _request_with_retry("GET", f"/users/{uid}")
    return response.json()


def update_agent_preferences(uid: str, preferences: dict) -> dict:
    """
    Deep-merge new preference signals into the Agent-side profile.
    Does NOT touch allergies.

    Returns:
        {"uid": "...", "updated": True}
    """
    response = _request_with_retry(
        "PATCH", f"/users/{uid}", json={"preferences": preferences}
    )
    return response.json()


def update_agent_allergies(
    uid: str,
    confirmed: list[str],
    intolerances: list[str],
    severity: dict[str, str],
) -> dict:
    """
    FULL REPLACE of the Agent-side allergy profile.

    Always pass the complete current allergy state — this is NOT a merge.
    The Agent rebuilds allergy_flags[] automatically.

    Returns:
        {"uid": "...", "allergy_flags": [...], "updated": True}
    """
    payload = {
        "confirmed": confirmed,
        "intolerances": intolerances,
        "severity": severity,
    }
    response = _request_with_retry(
        "PATCH", f"/users/{uid}/allergies", json=payload
    )
    return response.json()


def delete_agent_user(uid: str) -> bool:
    """
    Delete a user and their interaction history from the Agent.

    Returns True on success, False if the user was already absent (404).
    """
    try:
        _request_with_retry("DELETE", f"/users/{uid}")
        return True
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.warning("delete_agent_user: uid %s not found in Agent — skipping", uid)
            return False
        raise


def get_agent_interactions(
    uid: str,
    limit: int = 20,
    offset: int = 0,
    include_response: bool = False,
) -> dict:
    """
    Retrieve paginated interaction history for a user.
    """
    params = {
        "limit": limit,
        "offset": offset,
        "include_response": str(include_response).lower(),
    }
    response = _request_with_retry(
        "GET", f"/users/{uid}/interactions", params=params
    )
    return response.json()


def clear_agent_interactions(uid: str) -> bool:
    """
    Clear all interaction history for a user. Keeps the user record.

    Returns True on success.
    """
    _request_with_retry("DELETE", f"/users/{uid}/interactions")
    return True
```

---

## 4. User Registration — Signup Hook

Modify the existing `signup` view to call the Agent immediately after saving the user.

```python
# core/views.py

import logging

from django.conf import settings
from django.core.mail import send_mail
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import User
from .serializers import UserSerializer
from . import agent_service

import requests as http_requests

logger = logging.getLogger(__name__)


@api_view(['POST'])
def signup(request):
    """
    Register a new user.

    1. Validate + save user to Django DB.
    2. Send verification email.
    3. Create the Agent-side profile (best-effort — failures are logged but
       do NOT fail the registration response).

    Request body:
        {
            "username": "john_doe",
            "email": "john@example.com",
            "password": "SecurePass123"
        }

    Response 200:
        {"message": "Signup successful. Check your email to verify."}
    """
    serializer = UserSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    user = serializer.save()

    # Send verification email
    verify_link = f"{settings.FRONTEND_BASE_URL}/verify/{user.auth_token}/"
    send_mail(
        subject="Verify your Kairos account",
        message=f"Click to verify your account: {verify_link}",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True,
    )

    # Create Agent-side user profile
    # This is best-effort: if the Agent is down at signup time,
    # the profile will be created on first use (lazy creation).
    uid = str(user.auth_token)
    try:
        result = agent_service.create_agent_user(uid)
        logger.info("Agent profile created for uid=%s created=%s", uid, result.get("created"))
    except http_requests.RequestException as exc:
        # Do NOT fail the signup — log and continue.
        # The Frontend's first chat turn will surface a 404, which the
        # Backend's lazy-creation middleware (§4.1) will catch and fix.
        logger.error(
            "Could not create Agent profile for uid=%s during signup: %s — "
            "will retry on first active use.",
            uid, exc,
        )

    return Response({"message": "Signup successful. Check your email to verify."})
```

### 4.1 Lazy Profile Creation Middleware (Resilience Pattern)

If the Agent was unreachable at signup time, create the profile lazily when the user first hits any authenticated endpoint:

```python
# core/middleware.py

import logging

import requests as http_requests
from django.utils.deprecation import MiddlewareMixin

from .models import User
from . import agent_service

logger = logging.getLogger(__name__)


class AgentProfileEnsureMiddleware(MiddlewareMixin):
    """
    If the request carries a valid X-Auth-Token (Backend session token) and
    the user's Agent profile does not exist yet (404), create it transparently.

    This covers the edge case where the Agent was down during signup.
    Only activates on authenticated requests — anonymous requests are ignored.
    """

    def process_request(self, request):
        auth_token = request.headers.get("X-Auth-Token")
        if not auth_token:
            return None

        try:
            user = User.objects.get(auth_token=auth_token, is_verified=True)
        except User.DoesNotExist:
            return None

        uid = str(user.auth_token)
        try:
            agent_service.get_agent_user(uid)
        except http_requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info(
                    "AgentProfileEnsureMiddleware: creating missing Agent profile for uid=%s",
                    uid,
                )
                try:
                    agent_service.create_agent_user(uid)
                except http_requests.RequestException:
                    pass  # Agent still down — will retry next request
        except http_requests.RequestException:
            pass  # Agent temporarily unreachable — log is in agent_service

        return None
```

Register the middleware in `settings.py`:

```python
MIDDLEWARE = [
    # ... existing middleware ...
    'core.middleware.AgentProfileEnsureMiddleware',
]
```

---

## 5. Login — Forwarding the UID to the Frontend

The Frontend needs the `auth_token` UUID to set as `X-User-ID` on every Agent chat call. The existing login already returns `auth_id` — this is correct. No change needed there; just document the contract.

```python
# core/views.py — updated login view

@api_view(['POST'])
def login(request):
    """
    Authenticate a user.

    Request body:
        {"email": "john@example.com", "password": "SecurePass123"}

    Response 200 (success):
        {
            "message": "Login successful",
            "auth_id": "550e8400-e29b-41d4-a716-446655440000"
        }

    The Frontend stores auth_id and forwards it as:
        - X-Auth-Token header on requests to the Backend
        - X-User-ID header on requests to the Agent chat endpoint

    auth_id IS the user's stable uid. It never changes after account creation.
    """
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response({"message": "Email and password are required."}, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"message": "Invalid email or password."}, status=401)

    # Using check_password once hashing is in place:
    # if not user.check_password(password):
    if user.password != password:   # replace with check_password() once hashing is added
        return Response({"message": "Invalid email or password."}, status=401)

    if not user.is_verified:
        return Response({"message": "Please verify your email before logging in."}, status=403)

    return Response({
        "message": "Login successful",
        "auth_id": str(user.auth_token),
        "username": user.username,
    })
```

### What the Frontend Does with `auth_id`

```
POST /chat
Headers:
  X-User-ID: <auth_id>          ← forwarded to Agent
  Content-Type: application/json
Body:
  {
    "message": "Find a quiet romantic restaurant",
    "conversation_history": [...]
  }
```

The Frontend never sends chat via the Backend — it calls the Agent directly. The Backend's only role in the chat flow is issuing `auth_id` at login.

---

## 6. Allergy Management Endpoints

The Backend must expose endpoints for users to manage their allergy profile. These views call `PATCH /users/{uid}/allergies` on the Agent.

> **Critical rule:** Always send the **full, current allergy state** — not just the changed fields. The Agent performs a full replace, not a merge. A partial update could leave stale allergens that cause incorrect safety filtering.

### 6.1 Allergy Model Extension (Optional but Recommended)

Store a local copy of allergy data in Django so the Backend can always reconstruct the full state when a user changes one field:

```python
# core/models.py — add to existing file

import json

class UserAllergyProfile(models.Model):
    """
    Local mirror of the user's allergy profile.

    This is the source of truth for the Backend. The Agent stores its own
    copy and is always updated via PATCH /users/{uid}/allergies.
    Storing locally allows the Backend to reconstruct the full state on
    partial updates (e.g. user changes only severity of one allergen).
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='allergy_profile',
    )
    confirmed = models.JSONField(default=list)       # e.g. ["peanuts", "shellfish"]
    intolerances = models.JSONField(default=list)    # e.g. ["lactose"]
    severity = models.JSONField(default=dict)        # e.g. {"peanuts": "anaphylactic"}
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AllergyProfile({self.user.email})"
```

Run `python manage.py makemigrations && python manage.py migrate` after adding this model.

### 6.2 Serializer

```python
# core/serializers.py — add to existing file

from rest_framework import serializers
from .models import User, UserAllergyProfile

VALID_SEVERITIES = {"anaphylactic", "severe", "moderate", "intolerance"}

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


class AllergyProfileSerializer(serializers.Serializer):
    """Validates payload for PATCH /api/allergies/"""
    confirmed    = serializers.ListField(child=serializers.CharField(), default=list)
    intolerances = serializers.ListField(child=serializers.CharField(), default=list)
    severity     = serializers.DictField(child=serializers.CharField(), default=dict)

    def validate_severity(self, value: dict) -> dict:
        for allergen, level in value.items():
            if level not in VALID_SEVERITIES:
                raise serializers.ValidationError(
                    f"Invalid severity '{level}' for '{allergen}'. "
                    f"Must be one of: {', '.join(VALID_SEVERITIES)}"
                )
        return value

    def validate(self, data: dict) -> dict:
        # Every allergen in confirmed/intolerances must have a severity entry
        all_allergens = set(data.get("confirmed", [])) | set(data.get("intolerances", []))
        missing = all_allergens - set(data.get("severity", {}).keys())
        if missing:
            raise serializers.ValidationError(
                f"Missing severity for allergen(s): {', '.join(missing)}"
            )
        return data
```

### 6.3 Authentication Helper

Add a simple decorator to protect endpoints with the Backend's `auth_token`:

```python
# core/auth.py

import functools

from rest_framework.response import Response
from .models import User


def require_auth(view_func):
    """
    Decorator that validates X-Auth-Token and injects `request.user_obj`.

    Usage:
        @api_view(['GET'])
        @require_auth
        def my_view(request):
            user = request.user_obj   # User instance
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = request.headers.get("X-Auth-Token")
        if not token:
            return Response({"message": "Authentication required."}, status=401)
        try:
            user = User.objects.get(auth_token=token, is_verified=True)
        except (User.DoesNotExist, ValueError):
            return Response({"message": "Invalid or expired token."}, status=401)
        request.user_obj = user
        return view_func(request, *args, **kwargs)
    return wrapper
```

### 6.4 Allergy Views

```python
# core/views.py — add these views

import requests as http_requests
from .auth import require_auth
from .models import UserAllergyProfile
from .serializers import AllergyProfileSerializer


@api_view(['GET'])
@require_auth
def get_allergies(request):
    """
    GET /api/allergies/

    Returns the current allergy profile for the authenticated user.
    Data is served from the local Django DB (no Agent round-trip).

    Headers:
        X-Auth-Token: <auth_id>

    Response 200:
        {
            "confirmed": ["peanuts"],
            "intolerances": ["lactose"],
            "severity": {"peanuts": "anaphylactic", "lactose": "intolerance"}
        }
    """
    user = request.user_obj
    try:
        profile = user.allergy_profile
        return Response({
            "confirmed":    profile.confirmed,
            "intolerances": profile.intolerances,
            "severity":     profile.severity,
        })
    except UserAllergyProfile.DoesNotExist:
        return Response({"confirmed": [], "intolerances": [], "severity": {}})


@api_view(['PUT'])
@require_auth
def update_allergies(request):
    """
    PUT /api/allergies/

    Full replace of the user's allergy profile.
    Validates the payload, saves it locally, then propagates to the Agent.

    This is a PUT (not PATCH) because the semantics are full replacement on
    both the Backend and Agent sides.

    Headers:
        X-Auth-Token: <auth_id>
        Content-Type: application/json

    Request body:
        {
            "confirmed": ["peanuts", "shellfish"],
            "intolerances": ["lactose"],
            "severity": {
                "peanuts":   "anaphylactic",
                "shellfish": "severe",
                "lactose":   "intolerance"
            }
        }

    Response 200:
        {
            "message": "Allergy profile updated.",
            "allergy_flags": ["peanuts", "shellfish", "lactose"]
        }

    Response 400: validation errors
    Response 503: Agent unreachable (profile saved locally but not synced)
    """
    user = request.user_obj
    serializer = AllergyProfileSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    data = serializer.validated_data
    uid = str(user.auth_token)

    # 1. Save locally first (source of truth for the Backend)
    profile, _ = UserAllergyProfile.objects.get_or_create(user=user)
    profile.confirmed    = data["confirmed"]
    profile.intolerances = data["intolerances"]
    profile.severity     = data["severity"]
    profile.save()

    # 2. Propagate to Agent (critical safety path — retry up to 3×)
    try:
        result = agent_service.update_agent_allergies(
            uid=uid,
            confirmed=data["confirmed"],
            intolerances=data["intolerances"],
            severity=data["severity"],
        )
        return Response({
            "message": "Allergy profile updated.",
            "allergy_flags": result.get("allergy_flags", []),
        })
    except http_requests.RequestException as exc:
        # Saved locally but Agent sync failed.
        # Log an alert — this is a critical safety path.
        logger.critical(
            "ALLERGY SYNC FAILED for uid=%s: %s — "
            "Profile saved locally but Agent is out of sync. "
            "Operator action required.",
            uid, exc,
        )
        return Response(
            {
                "message": (
                    "Your allergy profile was saved but could not be synced "
                    "to the recommendation engine. Please try again in a moment."
                ),
                "error_code": "AGENT_SYNC_FAILED",
            },
            status=503,
        )


@api_view(['DELETE'])
@require_auth
def clear_allergies(request):
    """
    DELETE /api/allergies/

    Clears the user's entire allergy profile (sets all fields to empty).

    Headers:
        X-Auth-Token: <auth_id>

    Response 200:
        {"message": "Allergy profile cleared.", "allergy_flags": []}
    """
    user = request.user_obj
    uid = str(user.auth_token)

    # 1. Clear locally
    profile, _ = UserAllergyProfile.objects.get_or_create(user=user)
    profile.confirmed    = []
    profile.intolerances = []
    profile.severity     = {}
    profile.save()

    # 2. Propagate to Agent
    try:
        result = agent_service.update_agent_allergies(
            uid=uid,
            confirmed=[],
            intolerances=[],
            severity={},
        )
        return Response({"message": "Allergy profile cleared.", "allergy_flags": []})
    except http_requests.RequestException as exc:
        logger.critical(
            "ALLERGY CLEAR SYNC FAILED for uid=%s: %s",
            uid, exc,
        )
        return Response(
            {"message": "Profile cleared locally but could not sync to the recommendation engine."},
            status=503,
        )
```

---

## 7. Preference Update Endpoint

The Backend can push explicit preference signals (e.g. from an onboarding survey) to the Agent. This is optional — the Agent's profiler updates preferences automatically from chat, but an onboarding survey gives better initial data.

```python
# core/views.py — add this view

class PreferenceSerializer(serializers.Serializer):
    preferences = serializers.DictField()

    def validate_preferences(self, value: dict) -> dict:
        allowed_keys = {
            "dietary", "vibes", "cuisine_affinity",
            "price_comfort", "location_bias"
        }
        unknown = set(value.keys()) - allowed_keys
        if unknown:
            raise serializers.ValidationError(
                f"Unknown preference key(s): {', '.join(unknown)}. "
                f"Allowed: {', '.join(allowed_keys)}"
            )
        return value


@api_view(['PATCH'])
@require_auth
def update_preferences(request):
    """
    PATCH /api/preferences/

    Push preference signals to the Agent. Use during onboarding or when the
    user explicitly updates taste preferences in settings.

    These preferences are MERGED (not replaced) with existing Agent-side data.
    The Agent's profiler will continue updating them from chat signals.

    DO NOT send allergy data here — use PUT /api/allergies/ instead.

    Headers:
        X-Auth-Token: <auth_id>
        Content-Type: application/json

    Request body:
        {
            "preferences": {
                "dietary": ["vegan"],
                "vibes": ["quiet", "romantic"],
                "price_comfort": ["$$", "$$$"]
            }
        }

    Response 200:
        {"message": "Preferences updated."}
    """
    user = request.user_obj
    serializer = PreferenceSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    uid = str(user.auth_token)

    try:
        agent_service.update_agent_preferences(
            uid=uid,
            preferences=serializer.validated_data["preferences"],
        )
        return Response({"message": "Preferences updated."})
    except http_requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            # Agent profile missing — create it then retry
            agent_service.create_agent_user(uid)
            agent_service.update_agent_preferences(
                uid=uid,
                preferences=serializer.validated_data["preferences"],
            )
            return Response({"message": "Preferences updated."})
        raise
    except http_requests.RequestException as exc:
        logger.error("Preference update failed for uid=%s: %s", uid, exc)
        return Response({"message": "Could not update preferences. Please try again."}, status=503)
```

---

## 8. Account Deletion Hook

When a user deletes their account, the Backend must also remove their Agent-side profile.

```python
# core/views.py — add this view

@api_view(['DELETE'])
@require_auth
def delete_account(request):
    """
    DELETE /api/account/

    Deletes the user's account from both the Backend and the Agent.

    Order:
        1. Delete from Agent first (so data is removed from the AI system).
        2. Delete from Backend DB.

    If Agent deletion fails, the Backend deletion is still performed and
    the Agent deletion is logged for manual cleanup.

    Headers:
        X-Auth-Token: <auth_id>

    Response 204: Account deleted.
    """
    user = request.user_obj
    uid = str(user.auth_token)

    # 1. Delete from Agent
    try:
        deleted = agent_service.delete_agent_user(uid)
        if deleted:
            logger.info("Agent profile deleted for uid=%s", uid)
        else:
            logger.info("Agent profile not found for uid=%s — already absent", uid)
    except http_requests.RequestException as exc:
        # Do not block account deletion if Agent is down.
        # Schedule cleanup manually or via a periodic task.
        logger.error(
            "Could not delete Agent profile for uid=%s: %s — "
            "Agent-side data may remain. Manual cleanup required.",
            uid, exc,
        )

    # 2. Delete from Backend DB (always proceed)
    user.delete()

    from rest_framework.response import Response as DRFResponse
    return DRFResponse(status=204)
```

---

## 9. Admin Utilities — Interaction History

These views let admins or support staff inspect a user's chat history.

```python
# core/views.py — add these views

@api_view(['GET'])
@require_auth
def get_my_interactions(request):
    """
    GET /api/interactions/?limit=20&offset=0

    Returns the authenticated user's chat history from the Agent.

    Headers:
        X-Auth-Token: <auth_id>

    Query params:
        limit   (int, default 20, max 100)
        offset  (int, default 0)

    Response 200:
        {
            "interactions": [
                {
                    "id": 42,
                    "user_query": "Find a quiet romantic restaurant",
                    "ui_type": "radar_comparison",
                    "restaurant_ids": [101, 205, 88],
                    "allergy_warnings_shown": true,
                    "allergens_flagged": ["peanuts"],
                    "created_at": "2026-02-27T10:30:00Z"
                }
            ],
            "total": 42,
            "limit": 20,
            "offset": 0
        }
    """
    user = request.user_obj
    uid = str(user.auth_token)

    try:
        limit  = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))
    except ValueError:
        return Response({"message": "limit and offset must be integers."}, status=400)

    limit = min(limit, 100)

    try:
        data = agent_service.get_agent_interactions(uid, limit=limit, offset=offset)
        return Response(data)
    except http_requests.RequestException as exc:
        logger.error("Could not fetch interactions for uid=%s: %s", uid, exc)
        return Response({"message": "Could not load history. Please try again."}, status=503)


@api_view(['DELETE'])
@require_auth
def clear_my_interactions(request):
    """
    DELETE /api/interactions/

    Clears all of the authenticated user's chat history.

    Headers:
        X-Auth-Token: <auth_id>

    Response 204: History cleared.
    """
    user = request.user_obj
    uid = str(user.auth_token)

    try:
        agent_service.clear_agent_interactions(uid)
        return Response(status=204)
    except http_requests.RequestException as exc:
        logger.error("Could not clear interactions for uid=%s: %s", uid, exc)
        return Response({"message": "Could not clear history. Please try again."}, status=503)
```

---

## 10. Error Handling & Retry Policy

### 10.1 Behaviour by Endpoint

| Agent Endpoint | On Failure | User Impact |
|---|---|---|
| `POST /users/{uid}` (signup) | Log, continue | None — profile created lazily on first use |
| `PATCH /users/{uid}/allergies` | Log CRITICAL, return 503 | Show error; user must retry — safety path |
| `DELETE /users/{uid}` (account) | Log ERROR, continue deletion | Account deleted from Backend; Agent data may linger |
| `PATCH /users/{uid}` (prefs) | Log ERROR, return 503 | Show "try again" message |
| `GET /users/{uid}/interactions` | Log ERROR, return 503 | Show "history unavailable" message |

### 10.2 Exception Types from `agent_service`

```python
import requests as http_requests

try:
    agent_service.update_agent_allergies(uid, ...)
except http_requests.HTTPError as exc:
    # 4xx error — check exc.response.status_code
    if exc.response.status_code == 404:
        # User not in Agent — auto-create or log
        pass
    elif exc.response.status_code == 401:
        # SERVICE_TOKEN mismatch — config error, alert immediately
        pass
    elif exc.response.status_code == 422:
        # Invalid payload — check exc.response.json()["detail"]
        pass
except http_requests.ConnectionError:
    # Agent unreachable (network/DNS failure)
    pass
except http_requests.Timeout:
    # Request exceeded AGENT_TIMEOUT_SECONDS
    pass
```

### 10.3 Interpreting Agent Error Bodies

All Agent 4xx responses follow this shape:

```json
{"detail": "User not found", "code": "USER_NOT_FOUND"}
```

| `code` | HTTP | Action |
|---|---|---|
| `USER_NOT_FOUND` | 404 | Call `POST /users/{uid}` to create, then retry |
| `INVALID_SERVICE_TOKEN` | 401 | **Config alert** — `AGENT_SERVICE_TOKEN` mismatch |
| `MISSING_USER_ID` | 400 | Bug — `uid` not passed to Agent |
| `AGENT_UNAVAILABLE` | 500 | Retry with backoff |
| `INVALID_PAYLOAD` | 422 | Fix the serializer validation |

---

## 11. Full URL Configuration

Update `core/urls.py` to include all new endpoints:

```python
# core/urls.py

from django.urls import path
from .views import (
    signup,
    login,
    verify_email,
    get_allergies,
    update_allergies,
    clear_allergies,
    update_preferences,
    delete_account,
    get_my_interactions,
    clear_my_interactions,
)

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('signup/',             signup),
    path('login/',              login),
    path('verify/<uuid:token>/', verify_email),

    # ── Account ───────────────────────────────────────────────────────────────
    path('account/',            delete_account),       # DELETE /api/account/

    # ── Allergy management ────────────────────────────────────────────────────
    path('allergies/',          get_allergies),        # GET
    path('allergies/',          update_allergies),     # PUT
    path('allergies/',          clear_allergies),      # DELETE

    # ── Preferences ───────────────────────────────────────────────────────────
    path('preferences/',        update_preferences),   # PATCH

    # ── Chat history ──────────────────────────────────────────────────────────
    path('interactions/',       get_my_interactions),  # GET
    path('interactions/',       clear_my_interactions),# DELETE
]
```

> **Note:** Django resolves multiple views at the same path by method via `api_view`. Since `api_view` handles method routing, registering the same path multiple times in `urlpatterns` does **not** work as expected. Instead, combine methods in a single view using a dispatch pattern:

```python
# core/views.py — combined allergy view

@api_view(['GET', 'PUT', 'DELETE'])
@require_auth
def allergies_view(request):
    if request.method == 'GET':
        return get_allergies(request)
    elif request.method == 'PUT':
        return update_allergies(request)
    elif request.method == 'DELETE':
        return clear_allergies(request)
```

```python
# core/urls.py — clean version

from django.urls import path
from .views import (
    signup, login, verify_email,
    allergies_view, update_preferences,
    delete_account, interactions_view,
)

urlpatterns = [
    path('signup/',              signup),
    path('login/',               login),
    path('verify/<uuid:token>/', verify_email),
    path('account/',             delete_account),    # DELETE
    path('allergies/',           allergies_view),    # GET / PUT / DELETE
    path('preferences/',         update_preferences),# PATCH
    path('interactions/',        interactions_view), # GET / DELETE
]
```

And in `beyondstars_backend/urls.py`:

```python
# beyondstars_backend/urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/',   admin.site.urls),
    path('api/',     include('core.urls')),
]
```

---

## 12. End-to-End Flow Diagrams

### 12.1 New User Registration

```
Browser                  Django Backend              Agent
   │                           │                       │
   │  POST /api/signup/        │                       │
   │  {email, password, ...}   │                       │
   │──────────────────────────►│                       │
   │                           │                       │
   │                    Save User to DB                 │
   │                    Send verification email         │
   │                           │                       │
   │                           │  POST /users/{uid}    │
   │                           │  X-Service-Token: ... │
   │                           │  {}                   │
   │                           │──────────────────────►│
   │                           │                       │
   │                           │  201 {"created": true}│
   │                           │◄──────────────────────│
   │                           │                       │
   │  200 {"message": "..."}   │                       │
   │◄──────────────────────────│                       │
```

### 12.2 Allergy Profile Update

```
Browser                  Django Backend              Agent
   │                           │                       │
   │  PUT /api/allergies/       │                       │
   │  X-Auth-Token: <uid>      │                       │
   │  {confirmed, severity...} │                       │
   │──────────────────────────►│                       │
   │                           │                       │
   │                    Validate payload               │
   │                    Save to UserAllergyProfile     │
   │                           │                       │
   │                           │  PATCH /users/{uid}/  │
   │                           │  allergies            │
   │                           │  X-Service-Token: ... │
   │                           │  {confirmed,severity} │
   │                           │──────────────────────►│
   │                           │                       │
   │                           │  200 {allergy_flags}  │
   │                           │◄──────────────────────│
   │                           │                       │
   │  200 {allergy_flags}      │                       │
   │◄──────────────────────────│                       │
   │                           │                       │
   │  (next chat turn)         │                       │
   │  POST /chat               │                       │
   │  X-User-ID: <uid>         │                       │
   │───────────────────────────────────────────────────►
   │                           │  AllergyGuard uses    │
   │                           │  updated profile      │
   │◄───────────────────────────────────────────────────
```

### 12.3 Account Deletion

```
Browser                  Django Backend              Agent
   │                           │                       │
   │  DELETE /api/account/     │                       │
   │  X-Auth-Token: <uid>      │                       │
   │──────────────────────────►│                       │
   │                           │                       │
   │                           │  DELETE /users/{uid}  │
   │                           │  X-Service-Token: ... │
   │                           │──────────────────────►│
   │                           │                       │
   │                           │  204 No Content       │
   │                           │  (user + interactions │
   │                           │   deleted)            │
   │                           │◄──────────────────────│
   │                           │                       │
   │                    user.delete()                  │
   │                    (Django DB)                    │
   │                           │                       │
   │  204 No Content           │                       │
   │◄──────────────────────────│                       │
```

---

## 13. Security Checklist

Before deploying to production, verify all of these:

- [ ] `AGENT_SERVICE_TOKEN` is at least 32 random characters — never reuse the Django `SECRET_KEY`
- [ ] `AGENT_SERVICE_TOKEN` is stored in server environment variables, not in source code or committed `.env`
- [ ] The Agent's `/users/*` endpoints are firewalled — only the Backend server IP can reach them
- [ ] The Agent's `ALLOWED_ORIGINS` includes only `kariosb.gokulp.online` and `kairos.gokulp.online` (not `*`)
- [ ] Passwords are hashed with `make_password()` — not stored plain-text
- [ ] `require_auth` decorator is applied to every view that touches user data
- [ ] Allergy sync failures trigger a CRITICAL log alert — not just a warning
- [ ] `AGENT_BASE_URL` uses HTTPS in production
- [ ] Token rotation procedure documented: update `AGENT_SERVICE_TOKEN` in **both** Agent and Backend env simultaneously
- [ ] `DEBUG = False` in production Django settings
- [ ] `ALLOWED_HOSTS` is set to the production domain in Django settings

---

*This report covers everything needed to integrate the Django Backend with the Kairos Agent. For the Agent API reference, see `Agent/docs/BACKEND_INTEGRATION_REPORT.md`. For questions, check the Agent README or raise an issue in the repository.*
