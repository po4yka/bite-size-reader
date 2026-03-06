"""Policy services for URL validation, timeout selection, and batch orchestration."""

from __future__ import annotations

import logging
from typing import Any

from app.adapters.telegram.message_router_helpers import process_url_batch
from app.core.url_utils import extract_domain

logger = logging.getLogger(__name__)


class URLBatchPolicyService:
    """Encapsulates URL security, timeout, and batch execution policy."""

    def __init__(
        self,
        *,
        max_concurrent: int = 4,
        max_retries: int = 2,
        initial_timeout_sec: float = 900.0,
        max_timeout_sec: float = 1800.0,
    ) -> None:
        self.max_concurrent = max(1, max_concurrent)
        self.max_retries = max(0, max_retries)
        self.initial_timeout_sec = max(1.0, initial_timeout_sec)
        self.max_timeout_sec = max(self.initial_timeout_sec, max_timeout_sec)

    async def compute_timeout(
        self,
        *,
        url: str,
        attempt: int,
        adaptive_timeout_service: Any | None,
    ) -> float:
        """Compute timeout for URL processing with optional adaptive estimates."""
        base_timeout = self.initial_timeout_sec

        if adaptive_timeout_service and getattr(adaptive_timeout_service, "enabled", False):
            try:
                domain = extract_domain(url)
                estimate = await adaptive_timeout_service.get_timeout(url=url, domain=domain)
                base_timeout = estimate.timeout_sec
                logger.debug(
                    "adaptive_timeout_selected",
                    extra={
                        "url": url,
                        "domain": domain,
                        "base_timeout_sec": base_timeout,
                        "source": estimate.source,
                        "confidence": estimate.confidence,
                        "attempt": attempt,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "adaptive_timeout_error_using_default",
                    extra={"url": url, "error": str(exc)},
                )

        current_timeout = float(base_timeout) * (1.5**attempt)
        return min(current_timeout, self.max_timeout_sec)

    async def apply_security_checks(
        self,
        *,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
        response_formatter: Any,
    ) -> list[str]:
        """Validate URL batch against size and URL validation policy."""
        if not urls:
            return []

        max_batch_urls = response_formatter.MAX_BATCH_URLS
        if len(urls) > max_batch_urls:
            await response_formatter.safe_reply(
                message,
                f"❌ Too many URLs ({len(urls)}). Maximum allowed: {max_batch_urls}.",
            )
            logger.warning(
                "url_batch_limit_exceeded",
                extra={"url_count": len(urls), "max_allowed": max_batch_urls, "uid": uid},
            )
            return []

        valid_urls: list[str] = []
        for url in urls:
            is_valid, error_msg = response_formatter._validate_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                logger.warning(
                    "invalid_url_submitted",
                    extra={"url": url, "error": error_msg, "uid": uid, "cid": correlation_id},
                )

        if not valid_urls:
            await response_formatter.send_error_notification(
                message,
                "no_urls_found",
                correlation_id,
                details="All submitted URLs failed security or validation checks.",
            )

        return valid_urls

    async def process_multiple_urls_parallel(
        self,
        *,
        message: Any,
        urls: list[str],
        uid: int,
        correlation_id: str,
        url_processor: Any,
        response_formatter: Any,
        request_repo: Any,
        user_repo: Any,
        adaptive_timeout_service: Any | None,
        llm_client: Any | None,
        batch_session_repo: Any | None,
        batch_config: Any | None,
        initial_message_id: int | None = None,
    ) -> None:
        """Run batch URL processing with controlled concurrency and retries."""
        max_concurrent = max(2, min(self.max_concurrent, len(urls)))

        async def _compute_timeout(url: str, attempt: int) -> float:
            return await self.compute_timeout(
                url=url,
                attempt=attempt,
                adaptive_timeout_service=adaptive_timeout_service,
            )

        await process_url_batch(
            message=message,
            urls=urls,
            uid=uid,
            correlation_id=correlation_id,
            url_processor=url_processor,
            response_formatter=response_formatter,
            request_repo=request_repo,
            user_repo=user_repo,
            max_concurrent=max_concurrent,
            max_retries=self.max_retries,
            compute_timeout_func=_compute_timeout,
            initial_message_id=initial_message_id,
            llm_client=llm_client,
            batch_session_repo=batch_session_repo,
            batch_config=batch_config,
        )
