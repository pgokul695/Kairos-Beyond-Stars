"""
Gemma service — wraps Google Generative AI calls.

Primary model  : GEMMA_MODEL         (default: gemini-2.5-flash)
Fallback model : GEMMA_FALLBACK_MODEL (default: gemma-3-12b-it)

On any error from the primary (quota exhaustion, 429, network, etc.) the
service automatically retries the same prompt on the fallback model before
raising GemmaError. This prevents free-tier Gemini quota limits from taking
down the entire chat pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.google_api_key)

_primary_model  = genai.GenerativeModel(settings.gemma_model)
_fallback_model = genai.GenerativeModel(settings.gemma_fallback_model)

PRIMARY_TIMEOUT_SECONDS  = 30
FALLBACK_TIMEOUT_SECONDS = 60   # larger model — needs more time

# gRPC / HTTP status codes that indicate quota exhaustion — trigger fallback
_QUOTA_INDICATORS = ("RESOURCE_EXHAUSTED", "429", "quota", "rate limit")


class GemmaError(Exception):
    """Raised when both primary and fallback models fail."""


def _is_quota_error(exc: Exception) -> bool:
    """Return True if the exception looks like a quota / rate-limit error."""
    msg = str(exc).lower()
    return any(indicator.lower() in msg for indicator in _QUOTA_INDICATORS)


async def _call_model(model: genai.GenerativeModel, prompt: str, timeout: int) -> str:
    """
    Call a single model with the given timeout.
    Raises the original exception on failure (caller decides whether to retry).
    """
    response = await asyncio.wait_for(
        asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3,
                max_output_tokens=2048,
            ),
        ),
        timeout=timeout,
    )
    return response.text.strip()


async def call_gemma(prompt: str) -> str:
    """
    Call the primary model; fall back to the fallback model on any failure.

    Strategy:
      1. Try primary (gemini-2.5-flash by default) once.
      2. On ANY exception (quota, timeout, network), log a warning and
         immediately try the fallback model (gemma-3-12b-it by default).
      3. If the fallback also fails, raise GemmaError.

    Returns the raw text response.
    """
    logger.debug("Gemma prompt (%s):\n%s", settings.gemma_model, prompt)

    # ── Attempt 1: primary model ─────────────────────────────────────────────
    try:
        text = await _call_model(_primary_model, prompt, PRIMARY_TIMEOUT_SECONDS)
        logger.debug("Primary model response:\n%s", text)
        return text
    except Exception as primary_exc:
        if _is_quota_error(primary_exc):
            logger.warning(
                "Primary model '%s' quota exhausted — switching to fallback '%s'",
                settings.gemma_model,
                settings.gemma_fallback_model,
            )
        else:
            logger.warning(
                "Primary model '%s' failed (%s) — switching to fallback '%s'",
                settings.gemma_model,
                primary_exc,
                settings.gemma_fallback_model,
            )

    # ── Attempt 2: fallback model ─────────────────────────────────────────────
    try:
        text = await _call_model(_fallback_model, prompt, FALLBACK_TIMEOUT_SECONDS)
        logger.info(
            "Fallback model '%s' succeeded.", settings.gemma_fallback_model
        )
        logger.debug("Fallback model response:\n%s", text)
        return text
    except Exception as fallback_exc:
        logger.error(
            "Fallback model '%s' also failed: %s",
            settings.gemma_fallback_model,
            fallback_exc,
        )
        raise GemmaError(
            f"Both primary ({settings.gemma_model}) and fallback "
            f"({settings.gemma_fallback_model}) models failed. "
            f"Last error: {fallback_exc}"
        ) from fallback_exc


def _strip_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from a string."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            lines[1:-1] if lines[-1].startswith("```") else lines[1:]
        )
    return cleaned.strip()


async def call_gemma_json(prompt: str) -> Any:
    """
    Call the model (with fallback) and parse the response as JSON.

    Strips markdown fences if present. Raises GemmaError on parse failure.
    """
    raw = await call_gemma(prompt)
    cleaned = _strip_fences(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse model JSON: %s\nRaw: %s", exc, raw)
        raise GemmaError(f"Invalid JSON from model: {exc}") from exc
