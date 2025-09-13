from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

import httpx


@dataclass
class LLMCallResult:
    status: str
    model: str | None
    response_text: str | None
    response_json: dict | None
    tokens_prompt: int | None
    tokens_completion: int | None
    cost_usd: float | None
    latency_ms: int | None
    error_text: str | None
    request_headers: dict | None = None
    request_messages: list[dict] | None = None
    endpoint: str | None = "/api/v1/chat/completions"


class OpenRouterClient:
    """Minimal OpenRouter Chat Completions client (async)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        fallback_models: list[str] | tuple[str, ...] | None = None,
        http_referer: str | None = None,
        x_title: str | None = None,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        audit: Callable[[str, str, Dict[str, Any]], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._fallback_models = list(fallback_models or [])
        self._timeout = timeout_sec
        self._base_url = "https://openrouter.ai/api/v1/chat/completions"
        self._http_referer = http_referer
        self._x_title = x_title
        self._max_retries = max(0, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._audit = audit

    async def chat(self, messages: List[Dict[str, str]], *, temperature: float = 0.2, request_id: int | None = None) -> LLMCallResult:
        models_to_try = [self._model] + self._fallback_models
        last_error_text = None
        last_data = None
        last_latency = None
        last_model_reported = None

        for model in models_to_try:
            for attempt in range(self._max_retries + 1):
                if self._audit:
                    self._audit(
                        "INFO",
                        "openrouter_attempt",
                        {"attempt": attempt, "model": model, "request_id": request_id},
                    )
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
                if self._http_referer:
                    headers["HTTP-Referer"] = self._http_referer
                if self._x_title:
                    headers["X-Title"] = self._x_title

                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }

                started = time.perf_counter()
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        resp = await client.post(self._base_url, headers=headers, json=body)
                    latency = int((time.perf_counter() - started) * 1000)
                    data = resp.json()
                    last_latency = latency
                    last_data = data
                    last_model_reported = data.get("model", model)

                    status_code = resp.status_code
                    # Extract text and usage
                    text = None
                    try:
                        choices = data.get("choices") or []
                        if choices:
                            text = choices[0].get("message", {}).get("content")
                    except Exception:
                        text = None

                    usage = data.get("usage") or {}
                    # redact Authorization
                    redacted_headers = dict(headers)
                    if "Authorization" in redacted_headers:
                        redacted_headers["Authorization"] = "REDACTED"

                    if status_code < 400:
                        if self._audit:
                            self._audit(
                                "INFO",
                                "openrouter_success",
                                {"attempt": attempt, "model": model, "status": status_code, "latency_ms": latency, "request_id": request_id},
                            )
                        return LLMCallResult(
                            status="ok",
                            model=last_model_reported,
                            response_text=text,
                            response_json=data,
                            tokens_prompt=usage.get("prompt_tokens"),
                            tokens_completion=usage.get("completion_tokens"),
                            cost_usd=None,
                            latency_ms=latency,
                            error_text=None,
                            request_headers=redacted_headers,
                            request_messages=messages,
                            endpoint="/api/v1/chat/completions",
                        )
                    # retryable?
                    if status_code in (429,) or status_code >= 500:
                        last_error_text = data.get("error") or str(data)
                        if attempt < self._max_retries:
                            await asyncio_sleep_backoff(self._backoff_base, attempt)
                            continue
                        else:
                            break  # move to next model
                    else:
                        # non-retryable error, return immediately
                        if self._audit:
                            self._audit(
                                "ERROR",
                                "openrouter_error",
                                {"attempt": attempt, "model": model, "status": status_code, "error": data.get("error"), "request_id": request_id},
                            )
                        redacted_headers = dict(headers)
                        redacted_headers["Authorization"] = "REDACTED"
                        return LLMCallResult(
                            status="error",
                            model=last_model_reported,
                            response_text=text,
                            response_json=data,
                            tokens_prompt=usage.get("prompt_tokens"),
                            tokens_completion=usage.get("completion_tokens"),
                            cost_usd=None,
                            latency_ms=latency,
                            error_text=data.get("error") or str(data),
                            request_headers=redacted_headers,
                            request_messages=messages,
                            endpoint="/api/v1/chat/completions",
                        )
                except Exception as e:  # noqa: BLE001
                    latency = int((time.perf_counter() - started) * 1000)
                    last_latency = latency
                    last_error_text = str(e)
                    if attempt < self._max_retries:
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                    else:
                        break  # next model

            # moving to fallback model
            if self._audit and model != models_to_try[-1]:
                self._audit(
                    "WARN",
                    "openrouter_fallback",
                    {"from_model": model, "to_model": models_to_try[models_to_try.index(model) + 1], "request_id": request_id},
                )

        # All models exhausted
        redacted_headers = {
            "Authorization": "REDACTED",
            "Content-Type": "application/json",
        }
        if self._audit:
            self._audit(
                "ERROR",
                "openrouter_exhausted",
                {"models_tried": models_to_try, "attempts_each": self._max_retries + 1, "error": last_error_text, "request_id": request_id},
            )
        return LLMCallResult(
            status="error",
            model=last_model_reported,
            response_text=None,
            response_json=last_data,
            tokens_prompt=None,
            tokens_completion=None,
            cost_usd=None,
            latency_ms=last_latency,
            error_text=last_error_text or "All retries and fallbacks exhausted",
            request_headers=redacted_headers,
            request_messages=messages,
            endpoint="/api/v1/chat/completions",
        )


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    # Exponential backoff with light jitter: (base * 2^attempt) * (1 +/- 0.25)
    import asyncio, random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
