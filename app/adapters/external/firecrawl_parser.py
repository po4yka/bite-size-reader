from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import truncate_log_content


class FirecrawlResult(BaseModel):
    """Normalized representation of a Firecrawl `/v1/scrape` response."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="High-level status of the crawl attempt.")
    http_status: int | None = Field(
        default=None, description="HTTP status code returned by Firecrawl."
    )
    content_markdown: str | None = Field(
        default=None, description="Markdown content returned by Firecrawl."
    )
    content_html: str | None = Field(
        default=None, description="HTML content returned by Firecrawl."
    )
    structured_json: dict[str, Any] | None = Field(
        default=None, description="Structured JSON payload from Firecrawl."
    )
    metadata_json: dict[str, Any] | None = Field(
        default=None, description="Metadata block supplied by Firecrawl."
    )
    links_json: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Outbound links metadata from Firecrawl."
    )
    response_success: bool | None = Field(
        default=None, description="Whether Firecrawl reported success."
    )
    response_error_code: str | None = Field(
        default=None, description="Firecrawl-provided error code, if any."
    )
    response_error_message: str | None = Field(
        default=None, description="Firecrawl-provided error message, if any."
    )
    response_details: dict[str, Any] | list[Any] | None = Field(
        default=None, description="Additional detail array/object from Firecrawl."
    )
    latency_ms: int | None = Field(
        default=None, description="Client-observed latency for the call."
    )
    error_text: str | None = Field(
        default=None, description="Client-derived error message, if any."
    )
    source_url: str | None = Field(default=None, description="URL that was submitted to Firecrawl.")
    endpoint: str | None = Field(
        default="/v1/scrape", description="Firecrawl endpoint that was called."
    )
    options_json: dict[str, Any] | None = Field(
        default=None, description="Options payload sent to Firecrawl."
    )
    correlation_id: str | None = Field(
        default=None, description="Firecrawl correlation identifier (cid)."
    )


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
        log_truncate_length: int = 1000,
        # Connection pooling parameters
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
        keepalive_expiry: float = 30.0,
        # Credit monitoring
        credit_warning_threshold: int = 1000,
        credit_critical_threshold: int = 100,
    ) -> None:
        # Security: Validate API key presence and format
        if not api_key or not isinstance(api_key, str):
            raise ValueError("API key is required")
        # Validate Bearer token format (should start with 'fc-' for Firecrawl)
        if not api_key.startswith("fc-"):
            raise ValueError("API key must start with 'fc-'")

        # Security: Validate timeout
        if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0:  # noqa: UP038
            raise ValueError("Timeout must be positive")
        if timeout_sec > 300:  # 5 minutes max
            raise ValueError("Timeout too large")

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise ValueError("Max retries must be between 0 and 10")
        # Allow zero to disable waits in tests; only negative is invalid
        if not isinstance(backoff_base, (int, float)) or backoff_base < 0:  # noqa: UP038
            raise ValueError("Backoff base must be non-negative")

        # Validate connection pooling parameters
        if not isinstance(max_connections, int) or max_connections < 1 or max_connections > 100:
            raise ValueError("Max connections must be between 1 and 100")
        if (
            not isinstance(max_keepalive_connections, int)
            or max_keepalive_connections < 1
            or max_keepalive_connections > 50
        ):
            raise ValueError("Max keepalive connections must be between 1 and 50")
        if (
            not isinstance(keepalive_expiry, (int, float))  # noqa: UP038
            or keepalive_expiry < 1.0
            or keepalive_expiry > 300.0
        ):
            raise ValueError("Keepalive expiry must be between 1.0 and 300.0 seconds")
        if (
            not isinstance(credit_warning_threshold, int)
            or credit_warning_threshold < 1
            or credit_warning_threshold > 10000
        ):
            raise ValueError("Credit warning threshold must be between 1 and 10000")
        if (
            not isinstance(credit_critical_threshold, int)
            or credit_critical_threshold < 1
            or credit_critical_threshold > 1000
        ):
            raise ValueError("Credit critical threshold must be between 1 and 1000")

        self._api_key = api_key
        self._timeout = int(timeout_sec)
        self._base_url = "https://api.firecrawl.dev/v1/scrape"
        self._max_retries = max(0, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._audit = audit
        self._logger = logging.getLogger(__name__)
        self._debug_payloads = bool(debug_payloads)
        self._log_truncate_length = int(log_truncate_length)

        # Connection pooling configuration
        self._max_connections = int(max_connections)
        self._max_keepalive_connections = int(max_keepalive_connections)
        self._keepalive_expiry = float(keepalive_expiry)
        self._credit_warning_threshold = int(credit_warning_threshold)
        self._credit_critical_threshold = int(credit_critical_threshold)

        # Create httpx connection pool
        self._limits = httpx.Limits(
            max_connections=self._max_connections,
            max_keepalive_connections=self._max_keepalive_connections,
            keepalive_expiry=self._keepalive_expiry,
        )
        self._client = httpx.AsyncClient(timeout=self._timeout, limits=self._limits)

    async def aclose(self) -> None:
        await self._client.aclose()

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
        body_base = {"url": url, "formats": ["markdown", "html"]}
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
                extra={
                    "attempt": attempt,
                    "url": url,
                    "mobile": cur_mobile,
                    "pdf": cur_pdf,
                    "request_id": request_id,
                },
            )
            started = time.perf_counter()
            try:
                json_body = {**body_base, "mobile": cur_mobile}
                if cur_pdf:
                    json_body["parsers"] = ["pdf"]
                if self._debug_payloads:
                    self._logger.debug("firecrawl_request_payload", extra={"json": json_body})
                resp = await self._client.post(self._base_url, headers=headers, json=json_body)
                latency = int((time.perf_counter() - started) * 1000)
                try:
                    data = resp.json()
                except json.JSONDecodeError as e:
                    last_error = f"invalid_json: {e}"
                    last_latency = latency
                    self._logger.error(
                        "firecrawl_invalid_json",
                        extra={"error": str(e), "status": resp.status_code},
                    )
                    if attempt < self._max_retries:
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                    return FirecrawlResult(
                        status="error",
                        http_status=resp.status_code,
                        content_markdown=None,
                        content_html=None,
                        structured_json=None,
                        metadata_json=None,
                        links_json=None,
                        response_success=None,
                        response_error_code=None,
                        response_error_message=None,
                        response_details=None,
                        latency_ms=latency,
                        error_text=last_error,
                        source_url=url,
                        endpoint="/v1/scrape",
                        options_json={
                            "formats": ["markdown", "html"],
                            "mobile": cur_mobile,
                            **({"parsers": ["pdf"]} if cur_pdf else {}),
                        },
                    )
                last_data = data
                last_latency = latency
                self._logger.debug(
                    "firecrawl_response",
                    extra={
                        "status": resp.status_code,
                        "latency_ms": latency,
                        "request_id": request_id,
                    },
                )
                if self._debug_payloads:
                    preview = {
                        "keys": list(data.keys()) if isinstance(data, dict) else None,
                        "markdown_len": (
                            len(data.get("markdown") or "") if isinstance(data, dict) else None
                        ),
                    }
                    self._logger.debug("firecrawl_response_payload", extra={"preview": preview})

                if resp.status_code < 400:
                    # Extract correlation ID if present
                    correlation_id = data.get("cid")

                    raw_success_field = data.get("success")
                    if isinstance(raw_success_field, bool):
                        response_success = raw_success_field
                    elif raw_success_field is None:
                        response_success = None
                    else:
                        response_success = bool(raw_success_field)
                    response_error_code = data.get("code")
                    response_details = data.get("details")

                    # Check if the response body contains an error even with 200 status
                    response_error = data.get("error")

                    # Debug logging to understand the response structure
                    markdown_len = (
                        len(data.get("markdown") or "") if isinstance(data, dict) else None
                    )
                    html_len = len(data.get("html") or "") if isinstance(data, dict) else None
                    data_items = None
                    if isinstance(data.get("data"), list):
                        data_items = len(data["data"])
                    elif isinstance(data.get("data"), dict):
                        data_items = 1

                    self._logger.debug(
                        "firecrawl_response_debug",
                        extra={
                            "status_code": resp.status_code,
                            "response_keys": list(data.keys()) if isinstance(data, dict) else None,
                            "error_field": response_error,
                            "error_type": type(response_error).__name__,
                            "success_field": data.get("success"),
                            "markdown_len": markdown_len,
                            "html_len": html_len,
                            "data_items": data_items,
                            "correlation_id": correlation_id,
                        },
                    )

                    # Check for various error indicators in the response
                    has_error = False
                    error_message = None

                    # Check for explicit error field
                    if response_error and response_error.strip():
                        has_error = True
                        error_message = response_error
                    # Check for success=false in response
                    elif data.get("success") is False:
                        has_error = True
                        error_message = data.get("message") or "Request failed (success=false)"
                    # Check if response has data array but it's empty or contains errors
                    elif "data" in data and isinstance(data["data"], list):
                        if not data["data"]:
                            has_error = True
                            error_message = "No data returned in response"
                        else:
                            # Check if all items in data array have errors
                            all_items_have_errors = all(
                                item.get("error") for item in data["data"] if isinstance(item, dict)
                            )
                            if all_items_have_errors and len(data["data"]) > 0:
                                has_error = True
                                error_message = (
                                    data["data"][0].get("error") or "All data items have errors"
                                )
                    elif isinstance(data.get("data"), dict) and data["data"].get("error"):
                        has_error = True
                        error_message = data["data"].get("error") or "Data object error"
                    # Check for no content in direct response
                    elif not data.get("markdown") and not data.get("html") and "data" not in data:
                        has_error = True
                        error_message = "No content returned"

                    if has_error:
                        last_error = error_message
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
                            "firecrawl_error",
                            extra={"status": resp.status_code, "error": last_error},
                        )
                        # Extract content from response even in error case (handle both direct and data array formats)
                        error_content_markdown = data.get("markdown")
                        error_content_html = data.get("html")
                        error_metadata = data.get("metadata")
                        error_links = data.get("links")

                        # If content is in data array, extract from first item
                        if (
                            not error_content_markdown
                            and not error_content_html
                            and "data" in data
                            and isinstance(data["data"], list)
                            and len(data["data"]) > 0
                        ):
                            first_item = data["data"][0]
                            if isinstance(first_item, dict):
                                error_content_markdown = first_item.get("markdown")
                                error_content_html = first_item.get("html")
                                error_metadata = first_item.get("metadata")
                                error_links = first_item.get("links")
                        if (
                            not error_content_markdown
                            and not error_content_html
                            and isinstance(data.get("data"), dict)
                        ):
                            obj = data["data"]
                            error_content_markdown = obj.get("markdown")
                            error_content_html = obj.get("html")
                            error_metadata = obj.get("metadata")
                            error_links = obj.get("links")

                        summary_preview_source = error_content_markdown or error_content_html or ""
                        self._logger.info(
                            "firecrawl_result_summary",
                            extra={
                                "status": "error",
                                "http_status": resp.status_code,
                                "latency_ms": latency,
                                "markdown_len": len(error_content_markdown or ""),
                                "html_len": len(error_content_html or ""),
                                "correlation_id": correlation_id,
                                "request_id": request_id,
                                "error": last_error,
                                "excerpt": truncate_log_content(summary_preview_source, 160),
                            },
                        )

                        return FirecrawlResult(
                            status="error",
                            http_status=resp.status_code,
                            content_markdown=error_content_markdown,
                            content_html=error_content_html,
                            structured_json=data.get("structured"),
                            metadata_json=error_metadata,
                            links_json=error_links,
                            response_success=response_success,
                            response_error_code=response_error_code,
                            response_error_message=error_message or response_error,
                            response_details=response_details,
                            latency_ms=latency,
                            error_text=last_error,
                            source_url=url,
                            endpoint="/v1/scrape",
                            options_json={
                                "formats": ["markdown", "html"],
                                "mobile": cur_mobile,
                                **({"parsers": ["pdf"]} if cur_pdf else {}),
                            },
                            correlation_id=correlation_id,
                        )

                    # No error in response body, treat as success
                    # Extract content from response (handle both direct and data array formats)
                    content_markdown = data.get("markdown")
                    content_html = data.get("html")
                    metadata = data.get("metadata")
                    links = data.get("links")

                    # If content is in data array, extract from first item
                    if (
                        not content_markdown
                        and not content_html
                        and "data" in data
                        and isinstance(data["data"], list)
                        and len(data["data"]) > 0
                    ):
                        first_item = data["data"][0]
                        if isinstance(first_item, dict):
                            content_markdown = first_item.get("markdown")
                            content_html = first_item.get("html")
                            metadata = first_item.get("metadata")
                            links = first_item.get("links")
                    if (
                        not content_markdown
                        and not content_html
                        and isinstance(data.get("data"), dict)
                    ):
                        obj = data["data"]
                        content_markdown = obj.get("markdown")
                        content_html = obj.get("html")
                        metadata = obj.get("metadata")
                        links = obj.get("links")

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
                    summary_preview_source = content_markdown or content_html or ""
                    self._logger.info(
                        "firecrawl_result_summary",
                        extra={
                            "status": "ok",
                            "http_status": resp.status_code,
                            "latency_ms": latency,
                            "markdown_len": len(content_markdown or ""),
                            "html_len": len(content_html or ""),
                            "correlation_id": correlation_id,
                            "request_id": request_id,
                            "excerpt": truncate_log_content(summary_preview_source, 160),
                        },
                    )
                    return FirecrawlResult(
                        status="ok",
                        http_status=resp.status_code,
                        content_markdown=content_markdown,
                        content_html=content_html,
                        structured_json=data.get("structured"),
                        metadata_json=metadata,
                        links_json=links,
                        response_success=response_success,
                        response_error_code=response_error_code,
                        response_error_message=None,
                        response_details=response_details,
                        latency_ms=latency,
                        error_text=None,
                        source_url=url,
                        endpoint="/v1/scrape",
                        options_json={
                            "formats": ["markdown", "html"],
                            "mobile": cur_mobile,
                            **({"parsers": ["pdf"]} if cur_pdf else {}),
                        },
                        correlation_id=correlation_id,
                    )

                # Handle rate limiting (429) with exponential backoff
                if resp.status_code == 429:
                    retry_after = data.get("retry_after", 60)  # Default to 60 seconds
                    last_error = data.get("error") or "Rate limit exceeded"
                    if attempt < self._max_retries:
                        self._logger.warning(
                            "firecrawl_rate_limit",
                            extra={
                                "status": resp.status_code,
                                "retry_after": retry_after,
                                "attempt": attempt,
                            },
                        )
                        # Use retry_after from response or exponential backoff
                        delay = min(retry_after, self._backoff_base * (2**attempt))
                        await asyncio.sleep(delay)
                        continue
                # Retry on 5xx
                elif resp.status_code >= 500:
                    last_error = data.get("error") or str(data)
                    if attempt < self._max_retries:
                        cur_mobile = not cur_mobile  # toggle mobile emulation on retry
                        if pdf_hint:
                            cur_pdf = not cur_pdf  # toggle pdf parser
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                # Non-retryable error - handle specific status codes
                error_message = data.get("error") or str(data)

                # Map specific HTTP status codes to meaningful error messages
                if resp.status_code == 400:
                    error_message = f"Bad Request: {error_message}"
                elif resp.status_code == 401:
                    error_message = f"Unauthorized: {error_message}"
                elif resp.status_code == 402:
                    error_message = f"Payment Required: {error_message}"
                elif resp.status_code == 404:
                    error_message = f"Not Found: {error_message}"
                elif resp.status_code == 429:
                    error_message = f"Rate Limit Exceeded: {error_message}"
                elif resp.status_code >= 500:
                    error_message = f"Server Error: {error_message}"

                if self._audit:
                    self._audit(
                        "ERROR",
                        "firecrawl_error",
                        {
                            "attempt": attempt,
                            "status": resp.status_code,
                            "error": error_message,
                            "pdf": cur_pdf,
                            "request_id": request_id,
                        },
                    )
                self._logger.error(
                    "firecrawl_error", extra={"status": resp.status_code, "error": error_message}
                )
                summary_preview_source = data.get("markdown") or data.get("html") or ""
                self._logger.info(
                    "firecrawl_result_summary",
                    extra={
                        "status": "error",
                        "http_status": resp.status_code,
                        "latency_ms": latency,
                        "markdown_len": len(data.get("markdown") or ""),
                        "html_len": len(data.get("html") or ""),
                        "correlation_id": data.get("cid") if isinstance(data, dict) else None,
                        "request_id": request_id,
                        "error": error_message,
                        "excerpt": truncate_log_content(summary_preview_source, 160),
                    },
                )
                raw_success_field = data.get("success")
                if isinstance(raw_success_field, bool):
                    response_success = raw_success_field
                elif raw_success_field is None:
                    response_success = None
                else:
                    response_success = bool(raw_success_field)
                response_error_code = data.get("code")
                response_details = data.get("details")
                response_error_message = data.get("error") or error_message
                return FirecrawlResult(
                    status="error",
                    http_status=resp.status_code,
                    content_markdown=data.get("markdown"),
                    content_html=data.get("html"),
                    structured_json=data.get("structured"),
                    metadata_json=data.get("metadata"),
                    links_json=data.get("links"),
                    response_success=response_success,
                    response_error_code=response_error_code,
                    response_error_message=response_error_message,
                    response_details=response_details,
                    latency_ms=latency,
                    error_text=error_message,
                    source_url=url,
                    endpoint="/v1/scrape",
                    options_json={
                        "formats": ["markdown", "html"],
                        "mobile": cur_mobile,
                        **({"parsers": ["pdf"]} if cur_pdf else {}),
                    },
                    correlation_id=data.get("cid"),
                )
            except Exception as e:  # noqa: BLE001
                raise_if_cancelled(e)
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
        last_markdown = None
        last_html = None
        last_correlation = None
        response_success = None
        response_error_code = None
        response_error_message = None
        response_details = None
        if isinstance(last_data, dict):
            last_markdown = last_data.get("markdown")
            last_html = last_data.get("html")
            last_correlation = last_data.get("cid")
            raw_success_field = last_data.get("success")
            if isinstance(raw_success_field, bool):
                response_success = raw_success_field
            elif raw_success_field is not None:
                response_success = bool(raw_success_field)
            response_error_code = last_data.get("code")
            response_error_message = last_data.get("error")
            response_details = last_data.get("details")
        self._logger.info(
            "firecrawl_result_summary",
            extra={
                "status": "error",
                "http_status": None,
                "latency_ms": last_latency,
                "markdown_len": len(last_markdown or ""),
                "html_len": len(last_html or ""),
                "correlation_id": last_correlation,
                "request_id": request_id,
                "error": last_error,
                "excerpt": truncate_log_content(last_markdown or last_html or "", 160),
            },
        )
        return FirecrawlResult(
            status="error",
            http_status=None,
            content_markdown=None,
            content_html=None,
            structured_json=None,
            metadata_json=None,
            links_json=None,
            response_success=response_success,
            response_error_code=response_error_code,
            response_error_message=response_error_message,
            response_details=response_details,
            latency_ms=last_latency,
            error_text=last_error,
            source_url=url,
            endpoint="/v1/scrape",
            options_json={
                "formats": ["markdown", "html"],
                "mobile": cur_mobile,
                **({"parsers": ["pdf"]} if pdf_hint else {}),
            },
        )


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
