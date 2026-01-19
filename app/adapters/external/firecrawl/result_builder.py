"""Result construction for Firecrawl API responses.

This module provides builders for:
- Success results
- Error results (various types)
- Fallback results (after retry exhaustion)
- Non-retryable error results
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.external.firecrawl.constants import FIRECRAWL_SCRAPE_ENDPOINT
from app.adapters.external.firecrawl.models import FirecrawlResult
from app.adapters.external.firecrawl.response_processor import ResponseProcessor
from app.core.logging_utils import truncate_log_content

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.options import FirecrawlOptionsBuilder
    from app.adapters.external.firecrawl.payload_logger import PayloadLogger


class ResultBuilder:
    """Builds FirecrawlResult objects for various response scenarios."""

    def __init__(
        self,
        options: FirecrawlOptionsBuilder,
        payload_logger: PayloadLogger | None = None,
    ) -> None:
        """Initialize ResultBuilder.

        Args:
            options: FirecrawlOptionsBuilder for generating options snapshots
            payload_logger: Optional payload logger for audit logging
        """
        self._options = options
        self._payload_logger = payload_logger
        self._logger = logging.getLogger(__name__)
        self._response_processor = ResponseProcessor()

    def build_success_result(
        self,
        *,
        data: dict[str, Any],
        latency: int,
        url: str,
        options_snapshot: dict[str, Any],
        request_id: int | None,
        cur_pdf: bool,
    ) -> FirecrawlResult:
        """Build a successful FirecrawlResult from response data.

        Args:
            data: Parsed response data
            latency: Response latency in milliseconds
            url: Source URL
            options_snapshot: Options used for the request
            request_id: Optional request identifier
            cur_pdf: Whether PDF parsing was enabled

        Returns:
            FirecrawlResult with status="ok"
        """
        correlation_id = data.get("cid")
        response_success = self._response_processor.coerce_success(data.get("success"))
        response_error_code = data.get("code")
        response_details = data.get("details")

        # Log response debug info
        if self._payload_logger:
            self._payload_logger.log_response_debug(data, correlation_id)

        # Check for errors in body
        has_error, error_message = self._response_processor.detect_error_in_body(data)
        if has_error:
            return self._build_error_payload_result(
                data=data,
                latency=latency,
                url=url,
                response_success=response_success,
                response_error_code=response_error_code,
                error_message=error_message or data.get("error"),
                response_details=response_details,
                options_snapshot=options_snapshot,
                correlation_id=correlation_id,
                request_id=request_id,
                cur_pdf=cur_pdf,
            )

        # Extract content
        content_markdown, content_html, metadata, links = (
            self._response_processor.extract_content_fields(data)
        )

        # Log success
        if self._payload_logger:
            self._payload_logger.log_success(
                attempt=0,
                status=data.get("status_code"),
                latency_ms=latency,
                pdf=cur_pdf,
                request_id=request_id,
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
            options_json=options_snapshot,
            correlation_id=correlation_id,
        )

    def _build_error_payload_result(
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
        request_id: int | None,
        cur_pdf: bool,
    ) -> FirecrawlResult:
        """Build error result when response has error in body but HTTP 2xx.

        Args:
            data: Parsed response data
            latency: Response latency in milliseconds
            url: Source URL
            response_success: Coerced success field value
            response_error_code: Error code from response
            error_message: Error message
            response_details: Additional details from response
            options_snapshot: Options used for the request
            correlation_id: Firecrawl correlation ID
            request_id: Optional request identifier
            cur_pdf: Whether PDF parsing was enabled

        Returns:
            FirecrawlResult with status="error"
        """
        if self._payload_logger:
            self._payload_logger.log_error(
                attempt=0,
                status=data.get("status_code"),
                error=error_message or "Unknown error",
                pdf=cur_pdf,
                request_id=request_id,
            )

        # Extract any partial content
        (
            error_content_markdown,
            error_content_html,
            error_metadata,
            error_links,
            summary_text,
            screenshots,
        ) = self._response_processor.extract_error_content(data)

        # Enrich metadata
        error_metadata_enriched = self._response_processor.enrich_metadata(
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
                "request_id": request_id,
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

    def build_error_result(
        self,
        http_status: int | None,
        latency: int | None,
        error_text: str | None,
        url: str,
        options_snapshot: dict[str, Any],
    ) -> FirecrawlResult:
        """Build a simple error result without response data.

        Args:
            http_status: HTTP status code (if available)
            latency: Response latency in milliseconds
            error_text: Error message
            url: Source URL
            options_snapshot: Options used for the request

        Returns:
            FirecrawlResult with status="error"
        """
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

    def build_non_retryable_error_result(
        self,
        *,
        data: dict[str, Any],
        http_status: int,
        latency: int,
        url: str,
        options_snapshot: dict[str, Any],
        request_id: int | None,
        cur_pdf: bool,
        error_message: str,
    ) -> FirecrawlResult:
        """Build error result for non-retryable HTTP errors (4xx).

        Args:
            data: Parsed response data
            http_status: HTTP status code
            latency: Response latency in milliseconds
            url: Source URL
            options_snapshot: Options used for the request
            request_id: Optional request identifier
            cur_pdf: Whether PDF parsing was enabled
            error_message: Mapped error message

        Returns:
            FirecrawlResult with status="error"
        """
        if self._payload_logger:
            self._payload_logger.log_error(
                attempt=0,  # Will be overridden by caller
                status=http_status,
                error=error_message,
                pdf=cur_pdf,
                request_id=request_id,
            )

        correlation_id = data.get("cid") if isinstance(data, dict) else None
        metadata_enriched = self._response_processor.enrich_metadata(data, data.get("metadata"))

        summary_preview_source = data.get("markdown") or data.get("html") or ""
        self._logger.info(
            "firecrawl_result_summary",
            extra={
                "status": "error",
                "http_status": http_status,
                "latency_ms": latency,
                "markdown_len": len(data.get("markdown") or ""),
                "html_len": len(data.get("html") or ""),
                "correlation_id": correlation_id,
                "request_id": request_id,
                "error": error_message,
                "excerpt": truncate_log_content(summary_preview_source, 160),
            },
        )

        response_success = self._response_processor.coerce_success(data.get("success"))
        response_error_code = data.get("code")
        response_details = data.get("details")
        response_error_message = data.get("error") or error_message

        return FirecrawlResult(
            status="error",
            http_status=http_status,
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
            correlation_id=correlation_id,
        )

    def build_fallback_result(
        self,
        *,
        last_error: str | None,
        last_latency: int | None,
        last_data: dict[str, Any] | None,
        url: str,
        cur_mobile: bool,
        pdf_hint: bool,
    ) -> FirecrawlResult:
        """Build fallback result after all retries exhausted.

        Args:
            last_error: Last error message encountered
            last_latency: Last response latency
            last_data: Last response data (if any)
            url: Source URL
            cur_mobile: Current mobile mode setting
            pdf_hint: Whether URL hints at PDF content

        Returns:
            FirecrawlResult with status="error"
        """
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
            response_success = self._response_processor.coerce_success(last_data.get("success"))
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
