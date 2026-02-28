"""
Gemma service — wraps Google Generative AI Gemma calls.
30 s timeout, 1 retry. Returns parsed JSON or raises GemmaError.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.config import settings

logger = logging.getLogger(__name__)

genai.configure(api_key=settings.google_api_key)

_model = genai.GenerativeModel(settings.gemma_model)

TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 2


class GemmaError(Exception):
    """Raised when the Gemma call fails after all retries."""


async def call_gemma(prompt: str) -> str:
    """
    Call the Gemma model with the given prompt and return the raw text response.

    Applies a 30 s timeout and 1 retry (2 total attempts).
    Logs the full prompt and response at DEBUG level.
    Raises GemmaError after exhausting retries.
    """
    logger.debug("Gemma prompt:\n%s", prompt)

    @retry(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=wait_fixed(2),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _attempt() -> str:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
            ),
            timeout=TIMEOUT_SECONDS,
        )
        text = response.text.strip()
        logger.debug("Gemma response:\n%s", text)
        return text

    try:
        return await _attempt()
    except Exception as exc:
        raise GemmaError(f"Gemma call failed: {exc}") from exc


async def call_gemma_json(prompt: str) -> Any:
    """
    Call Gemma and parse the response as JSON.

    Strips markdown fences if present. Raises GemmaError on parse failure.
    """
    raw = await call_gemma(prompt)
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Drop first and last fence lines
        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Gemma JSON: %s\nRaw: %s", exc, raw)
        raise GemmaError(f"Invalid JSON from Gemma: {exc}") from exc
