"""
Shared Gemini helper used by the catalog builder and (later) the Vibe DJ app.

Reliability rules learned while testing the models (see PLAN.md):
  - every call has a short timeout and only a couple of retries, so a busy model
    can't hang the app for minutes
  - if the main model is overloaded or gone (429/5xx/404/timeout), the same request
    is retried once on the fallback model
  - every call is logged with the model used, how long it took, and whether it failed
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, Type, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("gemini")

TIMEOUT_MS = 60_000      # per attempt
RETRY_ATTEMPTS = 2       # per model, so worst case is 2 tries on main + 2 on fallback
FALLBACK_CODES = {404, 429, 500, 502, 503, 504}

T = TypeVar("T", bound=BaseModel)


class GeminiError(RuntimeError):
    """Raised when both the main and fallback models fail."""


def _setting(name: str, default: Optional[str] = None) -> str:
    value = (os.environ.get(name) or default or "").strip().strip('"').strip("'")
    if not value:
        raise GeminiError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=_setting("GEMINI_API_KEY"),
            http_options=types.HttpOptions(
                timeout=TIMEOUT_MS,
                retry_options=types.HttpRetryOptions(attempts=RETRY_ATTEMPTS),
            ),
        )
    return _client


def model_chain() -> list:
    """Main model first, then the fallback (if it's different)."""
    main = _setting("GEMINI_MODEL", "gemini-3.8-flash")
    fallback = _setting("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
    return [main] if fallback == main else [main, fallback]


def _should_fall_back(exc: Exception) -> bool:
    if isinstance(exc, errors.APIError):
        return exc.code in FALLBACK_CODES
    if isinstance(exc, ValidationError):  # model returned JSON that doesn't fit the schema
        return True
    # timeouts and dropped connections come through as httpx / OS errors
    return "timeout" in type(exc).__name__.lower() or isinstance(exc, (ConnectionError, OSError))


EMBED_DIMS = 768          # smaller than the 3072 default: ~4x smaller index, same ranking quality for short texts
EMBED_BATCH = 100


def embed(texts: list, task_type: str = "RETRIEVAL_DOCUMENT") -> list:
    """Embed many texts. Returns one vector (list of floats) per text, in order.

    Each text is wrapped in its own Content: gemini-embedding-2 merges a plain list of
    strings into ONE embedding, which silently breaks search (found while testing).
    There is no fallback model here: vectors from different models can't be compared.
    """
    model = _setting("GEMINI_EMBED_MODEL", "gemini-embedding-2")
    config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBED_DIMS)
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        contents = [types.Content(parts=[types.Part(text=text)]) for text in batch]
        began = time.time()
        result = get_client().models.embed_content(model=model, contents=contents, config=config)
        if len(result.embeddings) != len(batch):
            raise GeminiError(f"asked for {len(batch)} embeddings, got {len(result.embeddings)}")
        vectors += [e.values for e in result.embeddings]
        log.info("embed ok model=%s n=%d seconds=%.1f", model, len(batch), time.time() - began)
    return vectors


FAST_THINKING = "low"     # 4x faster than the default in testing (2.2s vs 8.8s) for short app tasks


def thinking_for(model: str, level: Optional[str], include_thoughts: bool = False) -> Optional[types.ThinkingConfig]:
    """Thinking settings only for the main model; the fallback gets none in case it doesn't support them."""
    if level is None or model != model_chain()[0]:
        return None
    return types.ThinkingConfig(thinking_level=level, include_thoughts=include_thoughts)


def generate_json(prompt: str, schema: Type[T], system: Optional[str] = None,
                  temperature: float = 0.0, thinking_level: Optional[str] = None) -> T:
    """Ask Gemini for JSON that matches `schema` (a pydantic model) and return it parsed."""
    last_error: Optional[Exception] = None
    for model in model_chain():
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=thinking_for(model, thinking_level),
        )
        start = time.time()
        try:
            response = get_client().models.generate_content(model=model, contents=prompt, config=config)
            parsed = response.parsed if isinstance(response.parsed, schema) else schema.model_validate_json(response.text)
            log.info("gemini ok model=%s seconds=%.1f", model, time.time() - start)
            return parsed
        except Exception as exc:  # noqa: BLE001 - we log and decide below
            last_error = exc
            log.warning("gemini fail model=%s seconds=%.1f error=%s", model, time.time() - start, str(exc)[:200])
            if not _should_fall_back(exc):
                break
    raise GeminiError(f"All Gemini models failed. Last error: {last_error}") from last_error
