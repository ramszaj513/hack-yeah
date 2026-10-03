"""Thin async wrapper around the OpenAI Responses API.

Two things matter here and are easy to get wrong elsewhere:

1. Structured output schemas are hand-written rather than generated from
   Pydantic, because OpenAI strict mode requires every object to set
   ``additionalProperties: false`` and list every property in ``required``.
2. Web-search citations are extracted *per call*. A call that verifies one
   claim yields grounding URLs for that claim only — collecting them across a
   multi-claim response and attaching them to everything fabricates citations.
"""

from __future__ import annotations

import json
from typing import Any

from app.config import settings


class LLMUnavailable(RuntimeError):
    """Raised when no API key is configured or the provider call fails."""


class Usage:
    """Running token totals, so prompt-cache savings are visible rather than assumed."""

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.cached_tokens = 0
        self.output_tokens = 0

    def record(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.calls += 1
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        details = getattr(usage, "input_tokens_details", None)
        self.cached_tokens += getattr(details, "cached_tokens", 0) or 0

    @property
    def cached_share(self) -> float:
        return self.cached_tokens / self.input_tokens if self.input_tokens else 0.0

    def summary(self) -> str:
        return (
            f"{self.calls} calls · input {self.input_tokens:,} "
            f"(cached {self.cached_tokens:,} = {self.cached_share:.0%}) · output {self.output_tokens:,}"
        )

    def reset(self) -> None:
        self.__init__()


usage = Usage()


def _client():
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise LLMUnavailable("The 'openai' package is not installed.") from exc

    key = settings().openai_api_key
    if not key:
        raise LLMUnavailable("OPENAI_API_KEY is not configured.")
    return AsyncOpenAI(api_key=key, timeout=settings().http_timeout_seconds * 3)


def grounding_urls(response: Any) -> list[str]:
    """Collect url_citation annotations from a single response.

    Only ever call this on a response scoped to one claim.
    """
    urls: list[str] = []
    seen: set[str] = set()

    try:
        payload = response.model_dump(mode="json", exclude_none=True)
    except Exception:
        return []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "url_citation":
                url = value.get("url")
                if isinstance(url, str) and url not in seen:
                    seen.add(url)
                    urls.append(url)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return urls


async def structured_call(
    *,
    prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    model: str | None = None,
    web_search: bool = False,
    max_output_tokens: int = 4096,
    cache_key: str | None = None,
    temperature: float | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Run one Responses call and return (parsed JSON, grounding URLs)."""

    config = settings()
    request: dict[str, Any] = {
        "model": model or config.openai_model,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": max_output_tokens,
    }
    chosen = config.temperature if temperature is None else temperature
    if chosen is not None:
        request["temperature"] = chosen
    if web_search:
        request["tools"] = [{"type": "web_search"}]
    if cache_key:
        # Segments the provider's prompt cache. Calls sharing a prefix must
        # also share this key, or each one lands in a different bucket and
        # nothing is reused.
        request["prompt_cache_key"] = cache_key

    client = _client()
    try:
        response = await client.responses.create(**request)
    except Exception as exc:
        raise LLMUnavailable(str(exc)) from exc

    usage.record(response)

    text = getattr(response, "output_text", "") or ""
    if not text.strip():
        raise LLMUnavailable("The model returned an empty response.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"The model returned invalid JSON: {text[:400]}") from exc

    return parsed, grounding_urls(response)
