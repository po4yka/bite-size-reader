"""Firecrawl v2 async client (scrape, search, crawl, batch, extract).

This module provides the main FirecrawlClient class which orchestrates:
- Content scraping with retry logic
- Search queries
- Crawl operations (async and sync)
- Batch scrape operations
- Data extraction

The client delegates to specialized modules for:
- Input validation (validators.py)
- Error handling and retries (error_handler.py)
- Response processing (response_processor.py)
- Result building (result_builder.py)
- Logging (payload_logger.py)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from app.adapters.external.firecrawl.constants import (
    FIRECRAWL_BATCH_SCRAPE_URL,
    FIRECRAWL_CRAWL_URL,
    FIRECRAWL_EXTRACT_URL,
    FIRECRAWL_SCRAPE_URL,
    FIRECRAWL_SEARCH_URL,
)
from app.adapters.external.firecrawl.error_handler import ErrorHandler, asyncio_sleep_backoff
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
from app.adapters.external.firecrawl.payload_logger import PayloadLogger
from app.adapters.external.firecrawl.result_builder import ResultBuilder
from app.adapters.external.firecrawl.validators import (
    validate_init,
    validate_scrape_inputs,
    validate_search_inputs,
)
from app.core.async_utils import raise_if_cancelled
from app.core.http_utils import ResponseSizeError, validate_response_size

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.utils.circuit_breaker import CircuitBreaker


class FirecrawlClient:
    """Firecrawl v2 async client (scrape, search, crawl, batch, extract)."""

    def __init__(
        self,
        api_key: str,
        timeout_sec: int = 90,
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
        circuit_breaker: CircuitBreaker | None = None,
        wait_for_ms: int | None = None,
    ) -> None:
        validate_init(
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
        self._logger = logging.getLogger(__name__)
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
            wait_for_ms=wait_for_ms,
        )

        self._payload_logger = PayloadLogger(
            audit=audit,
            debug_payloads=debug_payloads,
            log_truncate_length=log_truncate_length,
        )

        self._error_handler = ErrorHandler(
            max_retries=max_retries,
            backoff_base=backoff_base,
            max_response_size_bytes=self._max_response_size_bytes,
            payload_logger=self._payload_logger,
        )

        self._result_builder = ResultBuilder(
            options=self._options,
            payload_logger=self._payload_logger,
        )

        self._limits = httpx.Limits(
            max_connections=int(max_connections),
            max_keepalive_connections=int(max_keepalive_connections),
            keepalive_expiry=float(keepalive_expiry),
        )
        self._client = httpx.AsyncClient(timeout=self._timeout, limits=self._limits)
        self._circuit_breaker = circuit_breaker

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Return the circuit breaker instance if configured."""
        return self._circuit_breaker

    def get_circuit_breaker_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        if self._circuit_breaker:
            return self._circuit_breaker.get_stats()
        return {"state": "disabled"}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        request_id: int | None = None,
    ) -> FirecrawlSearchResult:
        trimmed_query = validate_search_inputs(query, limit, request_id)

        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"query": trimmed_query, "numResults": limit, "page": 1}

        self._payload_logger.log_search_request(
            query=trimmed_query, limit=limit, request_id=request_id
        )

        started = time.perf_counter()
        try:
            resp = await self._client.post(FIRECRAWL_SEARCH_URL, headers=headers, json=body)
            await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl Search")
        except ResponseSizeError as exc:
            return self._error_handler.build_search_size_error(exc, trimmed_query, started)
        except httpx.HTTPError as exc:
            return self._error_handler.build_search_http_error(exc, trimmed_query, started)

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            return self._error_handler.build_search_invalid_json_error(exc, resp, latency)

        return self._process_search_response(data, resp.status_code, latency, trimmed_query, limit)

    def _process_search_response(
        self,
        data: dict[str, Any],
        status_code: int,
        latency: int,
        query: str,
        limit: int,
    ) -> FirecrawlSearchResult:
        """Process search response and build result."""
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
        if status_code >= 400 or raw_error:
            status = "error"
            final_error = raw_error or f"HTTP {status_code}"

        self._payload_logger.log_search_response(
            status=status,
            http_status=status_code,
            result_count=len(items),
            query=query,
            latency_ms=latency,
        )

        return FirecrawlSearchResult(
            status=status,
            http_status=status_code,
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
        status_check_timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Crawl a URL with polling for completion.

        Args:
            url: URL to crawl
            options: Optional crawl options
            poll_interval: Seconds between status checks
            timeout_sec: Overall timeout for the crawl operation
            status_check_timeout: Timeout for each individual status check request

        Returns:
            Crawl result dictionary with status and data
        """
        started = await self.start_crawl(url, options)
        job_id = started.get("jobId") or started.get("job_id") or started.get("id")
        if not job_id:
            return started

        deadline = time.time() + max(1, timeout_sec)
        while time.time() < deadline:
            try:
                # Wrap each status check with a timeout to prevent indefinite hangs
                status = await asyncio.wait_for(
                    self.get_crawl_status(str(job_id)),
                    timeout=status_check_timeout,
                )
            except TimeoutError:
                self._logger.warning(
                    "crawl_status_check_timeout",
                    extra={
                        "job_id": job_id,
                        "timeout_sec": status_check_timeout,
                        "url": url,
                    },
                )
                # Continue polling - one slow check shouldn't abort the crawl
                await asyncio.sleep(max(0.1, poll_interval))
                continue
            except Exception as exc:
                self._logger.error(
                    "crawl_status_check_error",
                    extra={
                        "job_id": job_id,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "url": url,
                    },
                )
                # On persistent errors, return error status
                return {"status": "error", "jobId": job_id, "error": str(exc)}

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
        validate_scrape_inputs(url, request_id)

        # Check circuit breaker before proceeding
        if self._circuit_breaker and not self._circuit_breaker.can_proceed():
            self._logger.warning(
                "firecrawl_circuit_breaker_open",
                extra={
                    "url": url,
                    "request_id": request_id,
                    "circuit_state": self._circuit_breaker.state.value,
                    "failure_count": self._circuit_breaker.failure_count,
                },
            )
            return FirecrawlResult(
                status="error",
                http_status=503,
                content_markdown=None,
                content_html=None,
                response_success=False,
                error_text="Service temporarily unavailable (circuit breaker open)",
                latency_ms=0,
                source_url=url,
            )

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
            self._payload_logger.log_scrape_attempt(
                attempt=attempt,
                url=url,
                mobile=cur_mobile,
                pdf=cur_pdf,
                request_id=request_id,
            )

            started = time.perf_counter()
            try:
                result = await self._execute_scrape_attempt(
                    headers=headers,
                    body_base=body_base,
                    cur_mobile=cur_mobile,
                    cur_pdf=cur_pdf,
                    pdf_hint=pdf_hint,
                    options_snapshot=options_snapshot,
                    attempt=attempt,
                    url=url,
                    request_id=request_id,
                    started=started,
                )
                if result is not None:
                    if isinstance(result, tuple):
                        # Retry signal: (should_toggle, delay, data, latency, error)
                        should_toggle, delay, last_data, last_latency, last_error = result
                        if should_toggle:
                            cur_mobile = not cur_mobile
                            if pdf_hint:
                                cur_pdf = not cur_pdf
                        await asyncio.sleep(delay)
                        continue
                    # Record circuit breaker success on successful result
                    if self._circuit_breaker and result.success:
                        self._circuit_breaker.record_success()
                    elif self._circuit_breaker and not result.success:
                        self._circuit_breaker.record_failure()
                    return result
            except Exception as exc:
                raise_if_cancelled(exc)
                latency = int((time.perf_counter() - started) * 1000)
                last_latency = latency
                last_error = str(exc)
                self._payload_logger.log_exception(str(exc), attempt)
                if attempt < self._max_retries:
                    cur_mobile = not cur_mobile
                    if pdf_hint:
                        cur_pdf = not cur_pdf
                    await asyncio_sleep_backoff(self._backoff_base, attempt)
                    continue
                break

        self._payload_logger.log_exhausted(
            attempts=self._max_retries + 1,
            error=last_error,
            request_id=request_id,
        )
        # Record circuit breaker failure when retries are exhausted
        if self._circuit_breaker:
            self._circuit_breaker.record_failure()

        return self._result_builder.build_fallback_result(
            last_error=last_error,
            last_latency=last_latency,
            last_data=last_data,
            url=url,
            cur_mobile=cur_mobile,
            pdf_hint=pdf_hint,
        )

    async def _execute_scrape_attempt(
        self,
        *,
        headers: dict[str, str],
        body_base: dict[str, Any],
        cur_mobile: bool,
        cur_pdf: bool,
        pdf_hint: bool,
        options_snapshot: dict[str, Any],
        attempt: int,
        url: str,
        request_id: int | None,
        started: float,
    ) -> FirecrawlResult | tuple[bool, float, dict | None, int | None, str | None] | None:
        """Execute a single scrape attempt.

        Returns:
            - FirecrawlResult if request completed (success or non-retryable error)
            - Tuple (should_toggle, delay, data, latency, error) for retry signal
            - None if exception should be handled by caller
        """
        json_body = {
            **body_base,
            **self._options.base_options(mobile=cur_mobile, pdf=cur_pdf),
        }
        self._payload_logger.log_request_payload(json_body)

        resp = await self._client.post(self._base_url, headers=headers, json=json_body)
        try:
            await validate_response_size(resp, self._max_response_size_bytes, "Firecrawl")
        except ResponseSizeError as size_exc:
            latency = int((time.perf_counter() - started) * 1000)
            error = str(size_exc)
            self._payload_logger.log_response_too_large(
                error=error,
                url=url,
                max_size_mb=self._max_response_size_bytes / (1024 * 1024),
            )
            if attempt < self._max_retries:
                await asyncio_sleep_backoff(self._backoff_base, attempt)
                return (False, 0, None, latency, error)  # Retry without toggle
            return self._result_builder.build_error_result(
                resp.status_code, latency, error, url, options_snapshot
            )

        latency = int((time.perf_counter() - started) * 1000)
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            error = f"invalid_json: {exc}"
            self._payload_logger.log_invalid_json(str(exc), resp.status_code)
            if attempt < self._max_retries:
                await asyncio_sleep_backoff(self._backoff_base, attempt)
                return (False, 0, None, latency, error)
            return self._result_builder.build_error_result(
                resp.status_code, latency, error, url, options_snapshot
            )

        self._payload_logger.log_response(
            status_code=resp.status_code, latency_ms=latency, request_id=request_id
        )
        self._payload_logger.log_response_payload(data)

        if resp.status_code < 400:
            return self._result_builder.build_success_result(
                data=data,
                latency=latency,
                url=url,
                options_snapshot=options_snapshot,
                request_id=request_id,
                cur_pdf=cur_pdf,
            )

        retry_delay, toggle_mobile = self._error_handler.handle_retryable_errors(
            resp=resp,
            data=data,
            attempt=attempt,
            cur_mobile=cur_mobile,
            cur_pdf=cur_pdf,
            pdf_hint=pdf_hint,
        )
        if retry_delay is not None:
            return (toggle_mobile, retry_delay, data, latency, None)

        error_message = data.get("error") or str(data)
        error_message = self._error_handler.map_status_error(resp.status_code, error_message)
        return self._result_builder.build_non_retryable_error_result(
            data=data,
            http_status=resp.status_code,
            latency=latency,
            url=url,
            options_snapshot=options_snapshot,
            request_id=request_id,
            cur_pdf=cur_pdf,
            error_message=error_message,
        )
