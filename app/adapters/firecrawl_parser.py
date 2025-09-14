from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class FirecrawlResult:
    status: str
    http_status: int | None
    content_markdown: str | None
    content_html: str | None
    structured_json: dict | None
    metadata_json: dict | None
    links_json: dict | None
    raw_response_json: dict | None
    latency_ms: int | None
    error_text: str | None
    source_url: str | None = None
    endpoint: str | None = "/v1/scrape"
    options_json: dict | None = None


class FirecrawlClient:
    """Minimal Firecrawl scrape client (async)."""

    def __init__(
        self,
        api_key: str,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
        debug_payloads: bool = False,
    ) -> None:
        # Security: Validate API key
        if not api_key or not isinstance(api_key, str):
            raise ValueError("API key is required")
        if len(api_key) < 10 or len(api_key) > 500:
            raise ValueError("API key appears invalid")

        # Security: Validate timeout
        if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
            raise ValueError("Timeout must be positive")
        if timeout_sec > 300:  # 5 minutes max
            raise ValueError("Timeout too large")

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        if not isinstance(backoff_base, int | float) or backoff_base <= 0:
            raise ValueError("Backoff base must be positive")

        self._api_key = api_key
        self._timeout = int(timeout_sec)
        self._base_url = "https://api.firecrawl.dev/v1/scrape"
        self._max_retries = max(0, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._audit = audit
        self._logger = logging.getLogger(__name__)
        self._debug_payloads = bool(debug_payloads)

    async def scrape_markdown(
        self, url: str, *, mobile: bool = True, request_id: int | None = None
    ) -> FirecrawlResult:
        # Security: Validate URL input
        if not url or not isinstance(url, str):
            raise ValueError("URL is required")
        if len(url) > 2048:
            raise ValueError("URL too long")

        # Security: Validate request_id
        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            raise ValueError("Invalid request_id")

        headers = {"Authorization": f"Bearer {self._api_key}"}
        body_base = {"url": url, "formats": ["markdown"]}
        last_data = None
        last_latency = None
        last_error = None
        cur_mobile = mobile
        # Heuristic: try PDF parser if URL hints at PDF
        pdf_hint = url.lower().endswith(".pdf") or "pdf" in url.lower()
        cur_pdf = pdf_hint
        for attempt in range(self._max_retries + 1):
            if self._audit:
                self._audit(
                    "INFO",
                    "firecrawl_attempt",
                    {
                        "attempt": attempt,
                        "url": url,
                        "mobile": cur_mobile,
                        "pdf": cur_pdf,
                        "request_id": request_id,
                    },
                )
            self._logger.debug(
                "firecrawl_request",
                extra={"attempt": attempt, "url": url, "mobile": cur_mobile, "pdf": cur_pdf},
            )
            started = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    json_body = {**body_base, "mobile": cur_mobile}
                    if cur_pdf:
                        json_body["parsers"] = ["pdf"]
                    if self._debug_payloads:
                        self._logger.debug("firecrawl_request_payload", extra={"json": json_body})
                    resp = await client.post(self._base_url, headers=headers, json=json_body)
                latency = int((time.perf_counter() - started) * 1000)
                data = resp.json()
                last_data = data
                last_latency = latency
                self._logger.debug(
                    "firecrawl_response", extra={"status": resp.status_code, "latency_ms": latency}
                )
                if self._debug_payloads:
                    preview = {
                        "keys": list(data.keys()) if isinstance(data, dict) else None,
                        "markdown_len": (
                            len(data.get("markdown", "")) if isinstance(data, dict) else None
                        ),
                    }
                    self._logger.debug("firecrawl_response_payload", extra={"preview": preview})

                if resp.status_code < 400:
                    if self._audit:
                        self._audit(
                            "INFO",
                            "firecrawl_success",
                            {
                                "attempt": attempt,
                                "status": resp.status_code,
                                "latency_ms": latency,
                                "pdf": cur_pdf,
                                "request_id": request_id,
                            },
                        )
                    return FirecrawlResult(
                        status="ok",
                        http_status=resp.status_code,
                        content_markdown=data.get("markdown"),
                        content_html=data.get("html"),
                        structured_json=data.get("structured"),
                        metadata_json=data.get("metadata"),
                        links_json=data.get("links"),
                        raw_response_json=data,
                        latency_ms=latency,
                        error_text=None,
                        source_url=url,
                        endpoint="/v1/scrape",
                        options_json={
                            "formats": ["markdown"],
                            "mobile": cur_mobile,
                            **({"parsers": ["pdf"]} if cur_pdf else {}),
                        },
                    )

                # Retry on 5xx
                if resp.status_code >= 500:
                    last_error = data.get("error") or str(data)
                    if attempt < self._max_retries:
                        cur_mobile = not cur_mobile  # toggle mobile emulation on retry
                        if pdf_hint:
                            cur_pdf = not cur_pdf  # toggle pdf parser
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                # Non-retryable error
                if self._audit:
                    self._audit(
                        "ERROR",
                        "firecrawl_error",
                        {
                            "attempt": attempt,
                            "status": resp.status_code,
                            "error": last_error,
                            "pdf": cur_pdf,
                            "request_id": request_id,
                        },
                    )
                self._logger.error(
                    "firecrawl_error", extra={"status": resp.status_code, "error": last_error}
                )
                return FirecrawlResult(
                    status="error",
                    http_status=resp.status_code,
                    content_markdown=data.get("markdown"),
                    content_html=data.get("html"),
                    structured_json=data.get("structured"),
                    metadata_json=data.get("metadata"),
                    links_json=data.get("links"),
                    raw_response_json=data,
                    latency_ms=latency,
                    error_text=data.get("error") or str(data),
                    source_url=url,
                    endpoint="/v1/scrape",
                    options_json={
                        "formats": ["markdown"],
                        "mobile": cur_mobile,
                        **({"parsers": ["pdf"]} if cur_pdf else {}),
                    },
                )
            except Exception as e:  # noqa: BLE001
                latency = int((time.perf_counter() - started) * 1000)
                last_latency = latency
                last_error = str(e)
                self._logger.error(
                    "firecrawl_exception", extra={"error": str(e), "attempt": attempt}
                )
                if attempt < self._max_retries:
                    cur_mobile = not cur_mobile
                    if pdf_hint:
                        cur_pdf = not cur_pdf
                    await asyncio_sleep_backoff(self._backoff_base, attempt)
                    continue
                break

        if self._audit:
            self._audit(
                "ERROR",
                "firecrawl_exhausted",
                {"attempts": self._max_retries + 1, "error": last_error, "request_id": request_id},
            )
        return FirecrawlResult(
            status="error",
            http_status=None,
            content_markdown=None,
            content_html=None,
            structured_json=None,
            metadata_json=None,
            links_json=None,
            raw_response_json=last_data,
            latency_ms=last_latency,
            error_text=last_error,
            source_url=url,
            endpoint="/v1/scrape",
            options_json={
                "formats": ["markdown"],
                "mobile": cur_mobile,
                **({"parsers": ["pdf"]} if pdf_hint else {}),
            },
        )


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
