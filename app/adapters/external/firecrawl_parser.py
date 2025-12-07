from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.core.logging_utils import truncate_log_content

if TYPE_CHECKING:
    from collections.abc import Callable


FIRECRAWL_BASE_URL = "https://api.firecrawl.dev"
FIRECRAWL_SCRAPE_ENDPOINT = "/v2/scrape"
FIRECRAWL_SEARCH_ENDPOINT = "/v2/search"
FIRECRAWL_SCRAPE_URL = f"{FIRECRAWL_BASE_URL}{FIRECRAWL_SCRAPE_ENDPOINT}"
FIRECRAWL_SEARCH_URL = f"{FIRECRAWL_BASE_URL}{FIRECRAWL_SEARCH_ENDPOINT}"


class FirecrawlResult(BaseModel):
    """Normalized representation of a Firecrawl `/v2/scrape` response."""

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
        default=FIRECRAWL_SCRAPE_ENDPOINT, description="Firecrawl endpoint that was called."
    )
    options_json: dict[str, Any] | None = Field(
        default=None, description="Options payload sent to Firecrawl."
    )
    correlation_id: str | None = Field(
        default=None, description="Firecrawl correlation identifier (cid)."
    )


class FirecrawlSearchItem(BaseModel):
    """Normalized representation of a Firecrawl `/v2/search` result item."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: str | None = None


class FirecrawlSearchResult(BaseModel):
    """Result container for Firecrawl search queries."""

    status: str
    http_status: int | None = None
    results: list[FirecrawlSearchItem] = Field(default_factory=list)
    total_results: int | None = None
    latency_ms: int | None = None
    error_text: str | None = None
    correlation_id: str | None = None


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
        # Response size limits
        max_response_size_mb: int = 50,
    ) -> None:
        # Security: Validate API key presence and format
        if not api_key or not isinstance(api_key, str):
            msg = "API key is required"
            raise ValueError(msg)
        # Validate Bearer token format (should start with 'fc-' for Firecrawl)
        if not api_key.startswith("fc-"):
            msg = "API key must start with 'fc-'"
            raise ValueError(msg)

        # Security: Validate timeout
        if not isinstance(timeout_sec, int | float) or timeout_sec <= 0:
            msg = "Timeout must be positive"
            raise ValueError(msg)
        if timeout_sec > 300:  # 5 minutes max
            msg = "Timeout too large"
            raise ValueError(msg)

        # Security: Validate retry parameters
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            msg = "Max retries must be between 0 and 10"
            raise ValueError(msg)
        # Allow zero to disable waits in tests; only negative is invalid
        if not isinstance(backoff_base, int | float) or backoff_base < 0:
            msg = "Backoff base must be non-negative"
            raise ValueError(msg)

        # Validate connection pooling parameters
        if not isinstance(max_connections, int) or max_connections < 1 or max_connections > 100:
            msg = "Max connections must be between 1 and 100"
            raise ValueError(msg)
        if (
            not isinstance(max_keepalive_connections, int)
            or max_keepalive_connections < 1
            or max_keepalive_connections > 50
        ):
            msg = "Max keepalive connections must be between 1 and 50"
            raise ValueError(msg)
        if (
            not isinstance(keepalive_expiry, int | float)
            or keepalive_expiry < 1.0
            or keepalive_expiry > 300.0
        ):
            msg = "Keepalive expiry must be between 1.0 and 300.0 seconds"
            raise ValueError(msg)
        if (
            not isinstance(credit_warning_threshold, int)
            or credit_warning_threshold < 1
            or credit_warning_threshold > 10000
        ):
            msg = "Credit warning threshold must be between 1 and 10000"
            raise ValueError(msg)
        if (
            not isinstance(credit_critical_threshold, int)
            or credit_critical_threshold < 1
            or credit_critical_threshold > 1000
        ):
            msg = "Credit critical threshold must be between 1 and 1000"
            raise ValueError(msg)

        # Validate max_response_size_mb
        if (
            not isinstance(max_response_size_mb, int)
            or max_response_size_mb < 1
            or max_response_size_mb > 1024
        ):
            msg = "Max response size must be between 1 and 1024 MB"
            raise ValueError(msg)

        self._api_key = api_key
        self._timeout = int(timeout_sec)
        self._base_url = FIRECRAWL_SCRAPE_URL
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
        self._max_response_size_bytes = int(max_response_size_mb) * 1024 * 1024

        # Create httpx connection pool
        self._limits = httpx.Limits(
            max_connections=self._max_connections,
            max_keepalive_connections=self._max_keepalive_connections,
            keepalive_expiry=self._keepalive_expiry,
        )
        self._client = httpx.AsyncClient(timeout=self._timeout, limits=self._limits)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        request_id: int | None = None,
    ) -> FirecrawlSearchResult:
        """Call Firecrawl's search endpoint and normalize the response."""
        trimmed_query = str(query or "").strip()
        if not trimmed_query:
            msg = "Search query is required"
            raise ValueError(msg)
        if len(trimmed_query) > 500:
            msg = "Search query too long"
            raise ValueError(msg)

        if not isinstance(limit, int):
            msg = "Search limit must be an integer"
            raise ValueError(msg)
        if limit <= 0 or limit > 10:
            msg = "Search limit must be between 1 and 10"
            raise ValueError(msg)

        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            msg = "Invalid request_id"
            raise ValueError(msg)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"query": trimmed_query, "numResults": limit, "page": 1}

        if self._audit:
            with contextlib.suppress(Exception):
                self._audit(
                    "INFO",
                    "firecrawl_search_request",
                    {"query": trimmed_query, "limit": limit, "request_id": request_id},
                )

        self._logger.debug(
            "firecrawl_search_request",
            extra={"query": trimmed_query, "limit": limit, "request_id": request_id},
        )

        started = time.perf_counter()
        try:
            resp = await self._client.post(FIRECRAWL_SEARCH_URL, headers=headers, json=body)

            # Validate response size before parsing
            await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Search")
        except ResponseSizeError as exc:
            latency = int((time.perf_counter() - started) * 1000)
            error_text = str(exc)
            self._logger.error(
                "firecrawl_search_response_too_large",
                extra={
                    "error": error_text,
                    "query": trimmed_query,
                    "max_size_mb": self._max_response_size_bytes / (1024 * 1024),
                },
            )
            if self._audit:
                with contextlib.suppress(Exception):
                    self._audit(
                        "ERROR",
                        "firecrawl_search_response_too_large",
                        {"error": error_text, "query": trimmed_query},
                    )
            return FirecrawlSearchResult(
                status="error",
                results=[],
                latency_ms=latency,
                error_text=f"Response too large: {error_text}",
                http_status=None,
            )
        except httpx.HTTPError as exc:
            latency = int((time.perf_counter() - started) * 1000)
            error_text = str(exc)
            self._logger.exception(
                "firecrawl_search_http_error",
                extra={"error": error_text, "query": trimmed_query},
            )
            if self._audit:
                with contextlib.suppress(Exception):
                    self._audit(
                        "ERROR",
                        "firecrawl_search_http_error",
                        {"error": error_text, "query": trimmed_query},
                    )
            return FirecrawlSearchResult(
                status="error",
                results=[],
                latency_ms=latency,
                error_text=error_text,
                http_status=None,
            )

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            error_text = f"invalid_json: {exc}"
            self._logger.exception(
                "firecrawl_search_invalid_json",
                extra={"error": error_text, "status": resp.status_code},
            )
            if self._audit:
                with contextlib.suppress(Exception):
                    self._audit(
                        "ERROR",
                        "firecrawl_search_invalid_json",
                        {"status": resp.status_code, "error": error_text},
                    )
            return FirecrawlSearchResult(
                status="error",
                results=[],
                latency_ms=latency,
                error_text=error_text,
                http_status=resp.status_code,
            )

        correlation_id = None
        if isinstance(data, dict):
            correlation_id = data.get("cid") or data.get("correlation_id")

        total_results = self._extract_total_results(data)
        raw_error = self._extract_error_message(data)
        raw_items = self._extract_result_items(data)

        items: list[FirecrawlSearchItem] = []
        seen_urls: set[str] = set()
        for raw in raw_items:
            normalized = self._normalize_search_item(raw)
            if normalized is None:
                continue
            if normalized.url in seen_urls:
                continue
            seen_urls.add(normalized.url)
            items.append(normalized)
            if len(items) >= limit:
                break

        status = "success"
        final_error: str | None = None

        if resp.status_code >= 400 or raw_error:
            status = "error"
            final_error = raw_error or f"HTTP {resp.status_code}"

        if self._audit:
            with contextlib.suppress(Exception):
                self._audit(
                    "INFO" if status == "success" else "ERROR",
                    "firecrawl_search_response",
                    {
                        "status": status,
                        "http_status": resp.status_code,
                        "result_count": len(items),
                        "query": trimmed_query,
                    },
                )

        self._logger.debug(
            "firecrawl_search_response",
            extra={
                "status": status,
                "http_status": resp.status_code,
                "results": len(items),
                "latency_ms": latency,
            },
        )

        return FirecrawlSearchResult(
            status=status,
            http_status=resp.status_code,
            results=items,
            total_results=total_results,
            latency_ms=latency,
            error_text=final_error,
            correlation_id=correlation_id,
        )

    @classmethod
    def _extract_total_results(cls, payload: Any) -> int | None:
        """Attempt to extract a total results count from the payload."""
        queue: list[Any] = [payload]
        seen: set[int] = set()
        while queue:
            current = queue.pop(0)
            if id(current) in seen:
                continue
            seen.add(id(current))

            if isinstance(current, dict):
                for key in ("totalResults", "total_results", "numResults", "total"):
                    value = current.get(key)
                    if isinstance(value, int) and value >= 0:
                        return value
                nested = current.get("data")
                if nested is not None:
                    queue.append(nested)
            elif isinstance(current, list):
                queue.extend(current)
        return None

    @classmethod
    def _extract_error_message(cls, payload: Any) -> str | None:
        """Extract an error message from Firecrawl payloads if present."""
        if isinstance(payload, dict):
            for key in ("error", "message"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            nested = payload.get("data")
            if nested is not None:
                nested_error = cls._extract_error_message(nested)
                if nested_error:
                    return nested_error
        elif isinstance(payload, list):
            for item in payload:
                nested_error = cls._extract_error_message(item)
                if nested_error:
                    return nested_error
        return None

    @classmethod
    def _extract_result_items(cls, payload: Any) -> list[dict[str, Any]]:
        """Locate the list of search result dictionaries within the payload."""
        queue: list[Any] = [payload]
        seen: set[int] = set()
        while queue:
            current = queue.pop(0)
            if id(current) in seen:
                continue
            seen.add(id(current))

            if isinstance(current, list):
                dict_items = [item for item in current if isinstance(item, dict)]
                url_items = [item for item in dict_items if cls._has_url_field(item)]
                if url_items:
                    return url_items
                queue.extend(current)
            elif isinstance(current, dict):
                if cls._has_url_field(current):
                    return [current]
                for key in ("results", "items", "data", "matches"):
                    if key in current:
                        queue.append(current[key])
        return []

    @staticmethod
    def _has_url_field(item: dict[str, Any]) -> bool:
        url_value = item.get("url") or item.get("link") or item.get("sourceUrl")
        return bool(isinstance(url_value, str) and url_value.strip())

    @classmethod
    def _normalize_search_item(cls, raw: dict[str, Any]) -> FirecrawlSearchItem | None:
        """Normalize a raw search item dictionary into ``FirecrawlSearchItem``."""
        url = cls._normalize_text(
            raw.get("url") or raw.get("link") or raw.get("sourceUrl") or raw.get("permalink")
        )
        if not url:
            return None

        title = (
            cls._normalize_text(raw.get("title") or raw.get("name") or raw.get("headline")) or url
        )

        snippet_source = (
            raw.get("snippet") or raw.get("description") or raw.get("summary") or raw.get("content")
        )
        snippet = cls._normalize_text(snippet_source)
        if snippet:
            snippet = " ".join(snippet.split())

        source_value: Any = raw.get("source") or raw.get("site") or raw.get("publisher")
        if isinstance(source_value, dict):
            source_value = source_value.get("name") or source_value.get("title")
        elif isinstance(source_value, list):
            parts = [cls._normalize_text(part) for part in source_value]
            source_value = ", ".join(part for part in parts if part)
        source = cls._normalize_text(source_value)

        published_raw = (
            raw.get("published_at")
            or raw.get("publishedAt")
            or raw.get("published")
            or raw.get("date")
        )
        if isinstance(published_raw, dict):
            published_raw = published_raw.get("iso") or published_raw.get("value")
        published = cls._normalize_text(published_raw)

        return FirecrawlSearchItem(
            title=title,
            url=url,
            snippet=snippet,
            source=source,
            published_at=published,
        )

    @staticmethod
    def _normalize_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, int | float):
            value = str(value)
        text = str(value).strip()
        return text or None

    async def scrape_markdown(
        self, url: str, *, mobile: bool = True, request_id: int | None = None
    ) -> FirecrawlResult:
        # Security: Validate URL input
        if not url or not isinstance(url, str):
            msg = "URL is required"
            raise ValueError(msg)
        if len(url) > 2048:
            msg = "URL too long"
            raise ValueError(msg)

        # Security: Validate request_id
        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            msg = "Invalid request_id"
            raise ValueError(msg)

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

                # Validate response size before parsing
                try:
                    await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl")
                except ResponseSizeError as size_exc:
                    latency = int((time.perf_counter() - started) * 1000)
                    last_error = str(size_exc)
                    last_latency = latency
                    self._logger.error(
                        "firecrawl_response_too_large",
                        extra={
                            "error": last_error,
                            "url": url,
                            "max_size_mb": self._max_response_size_bytes / (1024 * 1024),
                        },
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
                        error_text=f"Response too large: {last_error}",
                        source_url=url,
                        endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
                        options_json={
                            "formats": ["markdown", "html"],
                            "mobile": cur_mobile,
                            **({"parsers": ["pdf"]} if cur_pdf else {}),
                        },
                    )

                latency = int((time.perf_counter() - started) * 1000)
                try:
                    data = resp.json()
                except json.JSONDecodeError as e:
                    last_error = f"invalid_json: {e}"
                    last_latency = latency
                    self._logger.exception(
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
                        endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
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
                            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
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
                        endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
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
                    endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
                    options_json={
                        "formats": ["markdown", "html"],
                        "mobile": cur_mobile,
                        **({"parsers": ["pdf"]} if cur_pdf else {}),
                    },
                    correlation_id=data.get("cid"),
                )
            except Exception as e:
                raise_if_cancelled(e)
                latency = int((time.perf_counter() - started) * 1000)
                last_latency = latency
                last_error = str(e)
                self._logger.exception(
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
            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
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
