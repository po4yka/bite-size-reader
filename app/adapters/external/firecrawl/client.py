from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from app.adapters.external.firecrawl.constants import (
    FIRECRAWL_BATCH_SCRAPE_URL,
    FIRECRAWL_CRAWL_URL,
    FIRECRAWL_EXTRACT_URL,
    FIRECRAWL_SCRAPE_ENDPOINT,
    FIRECRAWL_SCRAPE_URL,
    FIRECRAWL_SEARCH_URL,
)
from app.adapters.external.firecrawl.models import (
    FirecrawlResult,
    FirecrawlSearchItem,
    FirecrawlSearchResult,
)
from app.adapters.external.firecrawl.options import FirecrawlOptionsBuilder
from app.adapters.external.firecrawl.parsing import (
    extract_error_message,
    extract_result_items,
    extract_total_results,
    normalize_search_item,
)
from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size
from app.core.logging_utils import truncate_log_content

if TYPE_CHECKING:
    from collections.abc import Callable


class FirecrawlClient:
    """Firecrawl v2 async client (scrape, search, crawl, batch, extract)."""

    def __init__(
        self,
        api_key: str,
        timeout_sec: int = 60,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        audit: Callable[[str, str, dict[str, Any]], None] | None = None,
        debug_payloads: bool = False,
        log_truncate_length: int = 1000,
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
        keepalive_expiry: float = 30.0,
        credit_warning_threshold: int = 1000,
        credit_critical_threshold: int = 100,
        max_response_size_mb: int = 50,
        max_age_seconds: int = 172_800,
        remove_base64_images: bool = True,
        block_ads: bool = True,
        skip_tls_verification: bool = True,
        include_markdown_format: bool = True,
        include_html_format: bool = True,
        include_links_format: bool = False,
        include_summary_format: bool = False,
        include_images_format: bool = False,
        enable_screenshot_format: bool = False,
        screenshot_full_page: bool = True,
        screenshot_quality: int = 80,
        screenshot_viewport_width: int | None = None,
        screenshot_viewport_height: int | None = None,
        json_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> None:
        self._validate_init(
            api_key=api_key,
            timeout_sec=timeout_sec,
            max_retries=max_retries,
            backoff_base=backoff_base,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
            credit_warning_threshold=credit_warning_threshold,
            credit_critical_threshold=credit_critical_threshold,
            max_response_size_mb=max_response_size_mb,
        )

        self._api_key = api_key
        self._timeout = int(timeout_sec)
        self._base_url = FIRECRAWL_SCRAPE_URL
        self._max_retries = max(0, int(max_retries))
        self._backoff_base = float(backoff_base)
        self._audit = audit
        self._logger = logging.getLogger(__name__)
        self._debug_payloads = bool(debug_payloads)
        self._log_truncate_length = int(log_truncate_length)
        self._max_response_size_bytes = int(max_response_size_mb) * 1024 * 1024

        self._options = FirecrawlOptionsBuilder(
            max_age_seconds=max_age_seconds,
            remove_base64_images=remove_base64_images,
            block_ads=block_ads,
            skip_tls_verification=skip_tls_verification,
            include_markdown_format=include_markdown_format,
            include_html_format=include_html_format,
            include_links_format=include_links_format,
            include_summary_format=include_summary_format,
            include_images_format=include_images_format,
            enable_screenshot_format=enable_screenshot_format,
            screenshot_full_page=screenshot_full_page,
            screenshot_quality=screenshot_quality,
            screenshot_viewport_width=screenshot_viewport_width,
            screenshot_viewport_height=screenshot_viewport_height,
            json_prompt=json_prompt,
            json_schema=json_schema,
        )

        self._limits = httpx.Limits(
            max_connections=int(max_connections),
            max_keepalive_connections=int(max_keepalive_connections),
            keepalive_expiry=float(keepalive_expiry),
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
        trimmed_query = self._validate_search_inputs(query, limit, request_id)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"query": trimmed_query, "numResults": limit, "page": 1}

        self._audit_safe(
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
            await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Search")
        except ResponseSizeError as exc:
            return self._search_size_error(exc, trimmed_query, started)
        except httpx.HTTPError as exc:
            return self._search_http_error(exc, trimmed_query, started)

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            return self._search_invalid_json(exc, resp, latency)

        correlation_id = data.get("cid") if isinstance(data, dict) else None
        total_results = extract_total_results(data)
        raw_error = extract_error_message(data)
        raw_items = extract_result_items(data)

        items: list[FirecrawlSearchItem] = []
        seen_urls: set[str] = set()
        for raw in raw_items:
            normalized = normalize_search_item(raw)
            if normalized is None or normalized.url in seen_urls:
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

        self._audit_safe(
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

    async def start_crawl(self, url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"url": url, **(options or {})}
        payload.setdefault("formats", self._options.build_formats())
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.post(FIRECRAWL_CRAWL_URL, headers=headers, json=payload)
        await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Crawl")
        return resp.json()

    async def get_crawl_status(self, job_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.get(f"{FIRECRAWL_CRAWL_URL}/{job_id}", headers=headers)
        await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Crawl")
        return resp.json()

    async def crawl(
        self,
        url: str,
        *,
        options: dict[str, Any] | None = None,
        poll_interval: float = 1.0,
        timeout_sec: int = 120,
    ) -> dict[str, Any]:
        started = await self.start_crawl(url, options)
        job_id = started.get("jobId") or started.get("job_id") or started.get("id")
        if not job_id:
            return started

        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            status = await self.get_crawl_status(str(job_id))
            state = status.get("status") or status.get("state")
            if state in {"completed", "success", "succeeded"}:
                return status
            if state in {"failed", "error", "cancelled"}:
                return status
            await asyncio.sleep(max(0.1, poll_interval))
        return {"status": "timeout", "jobId": job_id}

    async def start_batch_scrape(
        self, urls: list[str], options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {"urls": urls, **(options or {})}
        payload.setdefault("formats", self._options.build_formats())
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.post(FIRECRAWL_BATCH_SCRAPE_URL, headers=headers, json=payload)
        await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl BatchScrape")
        return resp.json()

    async def get_batch_scrape_status(self, job_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.get(f"{FIRECRAWL_BATCH_SCRAPE_URL}/{job_id}", headers=headers)
        await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl BatchScrape")
        return resp.json()

    async def extract(self, args: dict[str, Any]) -> dict[str, Any]:
        payload = dict(args)
        payload.setdefault("formats", self._options.build_formats())
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = await self._client.post(FIRECRAWL_EXTRACT_URL, headers=headers, json=payload)
        await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Extract")
        return resp.json()

    async def scrape_markdown(
        self, url: str, *, mobile: bool = True, request_id: int | None = None
    ) -> FirecrawlResult:
        self._validate_scrape_inputs(url, request_id)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body_base = {"url": url, "formats": self._options.build_formats()}
        last_data = None
        last_latency = None
        last_error = None
        cur_mobile = mobile
        pdf_hint = url.lower().endswith(".pdf") or "pdf" in url.lower()
        cur_pdf = pdf_hint
        for attempt in range(self._max_retries + 1):
            options_snapshot = self._options.options_snapshot(mobile=cur_mobile, pdf=cur_pdf)
            self._audit_safe(
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
                json_body = {
                    **body_base,
                    **self._options.base_options(mobile=cur_mobile, pdf=cur_pdf),
                }
                if self._debug_payloads:
                    self._logger.debug("firecrawl_request_payload", extra={"json": json_body})
                resp = await self._client.post(self._base_url, headers=headers, json=json_body)
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
                    return self._error_result(
                        resp.status_code,
                        latency,
                        last_error,
                        url,
                        options_snapshot,
                    )

                latency = int((time.perf_counter() - started) * 1000)
                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    last_error = f"invalid_json: {exc}"
                    last_latency = latency
                    self._logger.exception(
                        "firecrawl_invalid_json",
                        extra={"error": str(exc), "status": resp.status_code},
                    )
                    if attempt < self._max_retries:
                        await asyncio_sleep_backoff(self._backoff_base, attempt)
                        continue
                    return self._error_result(
                        resp.status_code,
                        latency,
                        last_error,
                        url,
                        options_snapshot,
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
                    return self._handle_success_response(
                        data=data,
                        latency=latency,
                        url=url,
                        correlation_id=data.get("cid"),
                        response_success=None,
                        response_error_code=None,
                        response_details=None,
                        options_snapshot=options_snapshot,
                        request_id=request_id,
                        cur_pdf=cur_pdf,
                    )

                retry_delay, toggle_mobile = self._handle_retryable_errors(
                    resp=resp,
                    data=data,
                    attempt=attempt,
                    cur_mobile=cur_mobile,
                    cur_pdf=cur_pdf,
                    pdf_hint=pdf_hint,
                )
                if retry_delay is not None:
                    if toggle_mobile:
                        cur_mobile = not cur_mobile
                        if pdf_hint:
                            cur_pdf = not cur_pdf
                    await asyncio.sleep(retry_delay)
                    continue

                return self._handle_non_retryable_error(
                    data=data,
                    resp=resp,
                    latency=latency,
                    url=url,
                    options_snapshot=options_snapshot,
                    request_id=request_id,
                    cur_pdf=cur_pdf,
                )
            except Exception as exc:
                raise_if_cancelled(exc)
                latency = int((time.perf_counter() - started) * 1000)
                last_latency = latency
                last_error = str(exc)
                self._logger.exception(
                    "firecrawl_exception", extra={"error": str(exc), "attempt": attempt}
                )
                if attempt < self._max_retries:
                    cur_mobile = not cur_mobile
                    if pdf_hint:
                        cur_pdf = not cur_pdf
                    await asyncio_sleep_backoff(self._backoff_base, attempt)
                    continue
                break

        self._audit_safe(
            "ERROR",
            "firecrawl_exhausted",
            {"attempts": self._max_retries + 1, "error": last_error, "request_id": request_id},
        )
        return self._fallback_result(
            last_error=last_error,
            last_latency=last_latency,
            last_data=last_data,
            url=url,
            cur_mobile=cur_mobile,
            pdf_hint=pdf_hint,
        )

    def _handle_success_response(
        self,
        *,
        data: dict[str, Any],
        latency: int,
        url: str,
        correlation_id: str | None,
        response_success: bool | None,
        response_error_code: str | None,
        response_details: dict[str, Any] | list[Any] | None,
        options_snapshot: dict[str, Any],
        request_id: int | None,
        cur_pdf: bool,
    ) -> FirecrawlResult:
        response_success = self._coerce_success(data.get("success"))
        response_error_code = data.get("code")
        response_details = data.get("details")

        response_error = data.get("error")
        markdown_len = len(data.get("markdown") or "") if isinstance(data, dict) else None
        html_len = len(data.get("html") or "") if isinstance(data, dict) else None
        data_items = None
        if isinstance(data.get("data"), list):
            data_items = len(data["data"])
        elif isinstance(data.get("data"), dict):
            data_items = 1

        self._logger.debug(
            "firecrawl_response_debug",
            extra={
                "status_code": data.get("status_code"),
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

        has_error, error_message = self._detect_error_in_body(data)
        if has_error:
            self._audit_safe(
                "ERROR",
                "firecrawl_error",
                {
                    "attempt": 0,
                    "status": data.get("status_code"),
                    "error": error_message,
                    "pdf": cur_pdf,
                    "request_id": request_id,
                },
            )
            self._logger.error(
                "firecrawl_error",
                extra={"status": data.get("status_code"), "error": error_message},
            )
            return self._error_payload_result(
                data=data,
                latency=latency,
                url=url,
                response_success=response_success,
                response_error_code=response_error_code,
                error_message=error_message or response_error,
                response_details=response_details,
                options_snapshot=options_snapshot,
                correlation_id=correlation_id,
            )

        content_markdown, content_html, metadata, links = self._extract_content_fields(data)
        metadata_enriched = self._enrich_metadata(data, metadata)

        self._audit_safe(
            "INFO",
            "firecrawl_success",
            {
                "attempt": 0,
                "status": data.get("status_code"),
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
                "http_status": data.get("status_code"),
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
            http_status=data.get("status_code"),
            content_markdown=content_markdown,
            content_html=content_html,
            structured_json=data.get("structured"),
            metadata_json=metadata_enriched,
            links_json=links,
            response_success=response_success,
            response_error_code=response_error_code,
            response_error_message=None,
            response_details=response_details,
            latency_ms=latency,
            error_text=None,
            source_url=url,
            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
            options_json=options_snapshot,
            correlation_id=correlation_id,
        )

    def _handle_retryable_errors(
        self,
        *,
        resp: httpx.Response,
        data: dict[str, Any],
        attempt: int,
        cur_mobile: bool,
        cur_pdf: bool,
        pdf_hint: bool,
    ) -> tuple[float | None, bool]:
        if resp.status_code == 429:
            retry_after = data.get("retry_after", 60)
            if attempt < self._max_retries:
                self._logger.warning(
                    "firecrawl_rate_limit",
                    extra={
                        "status": resp.status_code,
                        "retry_after": retry_after,
                        "attempt": attempt,
                    },
                )
                delay = min(retry_after, self._backoff_base * (2**attempt))
                return delay, False
            return None, False
        if resp.status_code >= 500:
            if attempt < self._max_retries:
                delay = self._backoff_base * (2**attempt)
                return delay, True
        return None, False

    def _search_size_error(
        self, exc: ResponseSizeError, query: str, started: float
    ) -> FirecrawlSearchResult:
        latency = int((time.perf_counter() - started) * 1000)
        error_text = str(exc)
        self._logger.error(
            "firecrawl_search_response_too_large",
            extra={
                "error": error_text,
                "query": query,
                "max_size_mb": self._max_response_size_bytes / (1024 * 1024),
            },
        )
        self._audit_safe(
            "ERROR",
            "firecrawl_search_response_too_large",
            {"error": error_text, "query": query},
        )
        return FirecrawlSearchResult(
            status="error",
            results=[],
            latency_ms=latency,
            error_text=f"Response too large: {error_text}",
            http_status=None,
        )

    def _search_http_error(
        self, exc: httpx.HTTPError, query: str, started: float
    ) -> FirecrawlSearchResult:
        latency = int((time.perf_counter() - started) * 1000)
        error_text = str(exc)
        self._logger.exception(
            "firecrawl_search_http_error",
            extra={"error": error_text, "query": query},
        )
        self._audit_safe(
            "ERROR",
            "firecrawl_search_http_error",
            {"error": error_text, "query": query},
        )
        return FirecrawlSearchResult(
            status="error",
            results=[],
            latency_ms=latency,
            error_text=error_text,
            http_status=None,
        )

    def _search_invalid_json(
        self, exc: json.JSONDecodeError, resp: httpx.Response, latency: int
    ) -> FirecrawlSearchResult:
        error_text = f"invalid_json: {exc}"
        self._logger.exception(
            "firecrawl_search_invalid_json",
            extra={"error": error_text, "status": resp.status_code},
        )
        self._audit_safe(
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

    def _handle_non_retryable_error(
        self,
        *,
        data: dict[str, Any],
        resp: httpx.Response,
        latency: int,
        url: str,
        options_snapshot: dict[str, Any],
        request_id: int | None,
        cur_pdf: bool,
    ) -> FirecrawlResult:
        error_message = data.get("error") or str(data)
        error_message = self._map_status_error(resp.status_code, error_message)

        self._audit_safe(
            "ERROR",
            "firecrawl_error",
            {
                "attempt": self._max_retries,
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
        metadata_enriched = self._enrich_metadata(data, data.get("metadata"))
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
        response_success = self._coerce_success(data.get("success"))
        response_error_code = data.get("code")
        response_details = data.get("details")
        response_error_message = data.get("error") or error_message
        return FirecrawlResult(
            status="error",
            http_status=resp.status_code,
            content_markdown=data.get("markdown"),
            content_html=data.get("html"),
            structured_json=data.get("structured"),
            metadata_json=metadata_enriched,
            links_json=data.get("links"),
            response_success=response_success,
            response_error_code=response_error_code,
            response_error_message=response_error_message,
            response_details=response_details,
            latency_ms=latency,
            error_text=error_message,
            source_url=url,
            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
            options_json=options_snapshot,
            correlation_id=data.get("cid"),
        )

    def _error_payload_result(
        self,
        *,
        data: dict[str, Any],
        latency: int,
        url: str,
        response_success: bool | None,
        response_error_code: str | None,
        error_message: str | None,
        response_details: dict[str, Any] | list[Any] | None,
        options_snapshot: dict[str, Any],
        correlation_id: str | None,
    ) -> FirecrawlResult:
        error_content_markdown = data.get("markdown")
        error_content_html = data.get("html")
        error_metadata = data.get("metadata")
        error_links = data.get("links")
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")

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
                summary_text = summary_text or first_item.get("summary")
                screenshots = (
                    screenshots or first_item.get("screenshots") or first_item.get("images")
                )
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
            summary_text = summary_text or obj.get("summary")
            screenshots = screenshots or obj.get("screenshots") or obj.get("images")

        error_metadata_enriched = self._enrich_metadata(
            {"summary": summary_text, "screenshots": screenshots},
            error_metadata,
        )

        summary_preview_source = error_content_markdown or error_content_html or ""
        self._logger.info(
            "firecrawl_result_summary",
            extra={
                "status": "error",
                "http_status": data.get("status_code"),
                "latency_ms": latency,
                "markdown_len": len(error_content_markdown or ""),
                "html_len": len(error_content_html or ""),
                "correlation_id": correlation_id,
                "request_id": None,
                "error": error_message,
                "excerpt": truncate_log_content(summary_preview_source, 160),
            },
        )

        return FirecrawlResult(
            status="error",
            http_status=data.get("status_code"),
            content_markdown=error_content_markdown,
            content_html=error_content_html,
            structured_json=data.get("structured"),
            metadata_json=error_metadata_enriched,
            links_json=error_links,
            response_success=response_success,
            response_error_code=response_error_code,
            response_error_message=error_message,
            response_details=response_details,
            latency_ms=latency,
            error_text=error_message,
            source_url=url,
            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
            options_json=options_snapshot,
            correlation_id=correlation_id,
        )

    def _error_result(
        self,
        http_status: int | None,
        latency: int | None,
        error_text: str | None,
        url: str,
        options_snapshot: dict[str, Any],
    ) -> FirecrawlResult:
        return FirecrawlResult(
            status="error",
            http_status=http_status,
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
            error_text=error_text,
            source_url=url,
            endpoint=FIRECRAWL_SCRAPE_ENDPOINT,
            options_json=options_snapshot,
        )

    def _fallback_result(
        self,
        *,
        last_error: str | None,
        last_latency: int | None,
        last_data: dict[str, Any] | None,
        url: str,
        cur_mobile: bool,
        pdf_hint: bool,
    ) -> FirecrawlResult:
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
            response_success = self._coerce_success(last_data.get("success"))
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
                "request_id": None,
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
            options_json=self._options.options_snapshot(mobile=cur_mobile, pdf=pdf_hint),
        )

    @staticmethod
    def _coerce_success(raw_success: Any) -> bool | None:
        if isinstance(raw_success, bool):
            return raw_success
        if raw_success is None:
            return None
        return bool(raw_success)

    @staticmethod
    def _map_status_error(status_code: int, error_message: str) -> str:
        if status_code == 400:
            return f"Bad Request: {error_message}"
        if status_code == 401:
            return f"Unauthorized: {error_message}"
        if status_code == 402:
            return f"Payment Required: {error_message}"
        if status_code == 404:
            return f"Not Found: {error_message}"
        if status_code == 429:
            return f"Rate Limit Exceeded: {error_message}"
        if status_code >= 500:
            return f"Server Error: {error_message}"
        return error_message

    def _detect_error_in_body(self, data: dict[str, Any]) -> tuple[bool, str | None]:
        response_error = data.get("error")
        if response_error and str(response_error).strip():
            return True, str(response_error)
        if data.get("success") is False:
            return True, data.get("message") or "Request failed (success=false)"
        if "data" in data and isinstance(data["data"], list):
            if not data["data"]:
                return True, "No data returned in response"
            all_errors = all(item.get("error") for item in data["data"] if isinstance(item, dict))
            if all_errors and len(data["data"]) > 0:
                return True, data["data"][0].get("error") or "All data items have errors"
        if isinstance(data.get("data"), dict) and data["data"].get("error"):
            return True, data["data"].get("error") or "Data object error"
        if not data.get("markdown") and not data.get("html") and "data" not in data:
            return True, "No content returned"
        return False, None

    @staticmethod
    def _extract_content_fields(
        data: dict[str, Any],
    ) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any] | list[Any] | None]:
        content_markdown = data.get("markdown")
        content_html = data.get("html")
        metadata = data.get("metadata")
        links = data.get("links")
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")

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
                summary_text = summary_text or first_item.get("summary")
                screenshots = (
                    screenshots or first_item.get("screenshots") or first_item.get("images")
                )
        if not content_markdown and not content_html and isinstance(data.get("data"), dict):
            obj = data["data"]
            content_markdown = obj.get("markdown")
            content_html = obj.get("html")
            metadata = obj.get("metadata")
            links = obj.get("links")
            summary_text = summary_text or obj.get("summary")
            screenshots = screenshots or obj.get("screenshots") or obj.get("images")

        metadata_enriched = metadata
        if summary_text or screenshots:
            metadata_enriched = dict(metadata_enriched or {})
            if summary_text:
                metadata_enriched["summary_text"] = summary_text
            if screenshots:
                metadata_enriched["screenshots"] = screenshots

        return content_markdown, content_html, metadata_enriched, links

    def _enrich_metadata(
        self, data: dict[str, Any], base_metadata: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")
        metadata_enriched = base_metadata
        if summary_text or screenshots:
            metadata_enriched = dict(metadata_enriched or {})
            if summary_text:
                metadata_enriched["summary_text"] = summary_text
            if screenshots:
                metadata_enriched["screenshots"] = screenshots
        return metadata_enriched

    def _validate_search_inputs(self, query: str, limit: int, request_id: int | None) -> str:
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
        return trimmed_query

    @staticmethod
    def _validate_scrape_inputs(url: str, request_id: int | None) -> None:
        if not url or not isinstance(url, str):
            msg = "URL is required"
            raise ValueError(msg)
        if len(url) > 2048:
            msg = "URL too long"
            raise ValueError(msg)
        if request_id is not None and (not isinstance(request_id, int) or request_id <= 0):
            msg = "Invalid request_id"
            raise ValueError(msg)

    @staticmethod
    def _validate_init(
        *,
        api_key: str,
        timeout_sec: int | float,
        max_retries: int,
        backoff_base: float,
        max_connections: int,
        max_keepalive_connections: int,
        keepalive_expiry: float,
        credit_warning_threshold: int,
        credit_critical_threshold: int,
        max_response_size_mb: int,
    ) -> None:
        if not api_key or not isinstance(api_key, str):
            msg = "API key is required"
            raise ValueError(msg)
        if not api_key.startswith("fc-"):
            msg = "API key must start with 'fc-'"
            raise ValueError(msg)
        if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0 or timeout_sec > 300:
            msg = "Timeout must be positive and <=300s"
            raise ValueError(msg)
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            msg = "Max retries must be between 0 and 10"
            raise ValueError(msg)
        if not isinstance(backoff_base, (int, float)) or backoff_base < 0:
            msg = "Backoff base must be non-negative"
            raise ValueError(msg)
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
            not isinstance(keepalive_expiry, (int, float))
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
        if (
            not isinstance(max_response_size_mb, int)
            or max_response_size_mb < 1
            or max_response_size_mb > 1024
        ):
            msg = "Max response size must be between 1 and 1024 MB"
            raise ValueError(msg)

    def _audit_safe(self, level: str, event: str, details: dict[str, Any]) -> None:
        if not self._audit:
            return
        with contextlib.suppress(Exception):
            self._audit(level, event, details)


async def asyncio_sleep_backoff(base: float, attempt: int) -> None:
    import random

    base_delay = max(0.0, base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
