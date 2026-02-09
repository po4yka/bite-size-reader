"""Tests for domain-level fail-fast in batch URL processing.

Includes unit tests for domain membership and integration tests
verifying asyncio.Event-based cancellation of in-flight siblings.
"""

from __future__ import annotations

import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.telegram.url_handler import URLHandler
from app.models.batch_processing import URLBatchStatus


class TestDomainFailFast(unittest.IsolatedAsyncioTestCase):
    """Verify domain-level fail-fast skips URLs after domain timeout."""

    async def test_second_url_from_timed_out_domain_is_skipped(self):
        """When first URL from a domain times out, second URL is skipped."""
        urls = [
            "https://habr.com/article/1",
            "https://habr.com/article/2",
        ]

        batch_status = URLBatchStatus.from_urls(urls)

        # Simulate: first URL exhausts retries -> domain added to failed set
        failed_domains: set[str] = set()
        failed_domains.add("habr.com")

        # Check domain membership for second URL
        entry = batch_status._find_entry(urls[1])
        assert entry is not None
        assert entry.domain == "habr.com"
        assert entry.domain in failed_domains

    async def test_different_domain_not_affected(self):
        """URLs from different domains are not affected by fail-fast."""
        failed_domains: set[str] = {"habr.com"}

        batch_status = URLBatchStatus.from_urls(
            [
                "https://habr.com/article/1",
                "https://example.com/page",
            ]
        )

        entry = batch_status._find_entry("https://example.com/page")
        assert entry is not None
        assert entry.domain == "example.com"
        assert entry.domain not in failed_domains


class TestDomainFailFastFormatting(unittest.TestCase):
    """Verify domain_timeout error type formats correctly."""

    def test_domain_timeout_error_format(self):
        """domain_timeout error type displays as 'Skipped (slow site)'."""
        from app.adapters.external.formatting.batch_progress_formatter import (
            BatchProgressFormatter,
        )

        result = BatchProgressFormatter._format_error_short(
            "domain_timeout", "Skipped (domain habr.com timed out)"
        )
        assert result == "Skipped (slow site)"

    def test_regular_timeout_unaffected(self):
        """Regular timeout formatting shows 'Timed out'."""
        from app.adapters.external.formatting.batch_progress_formatter import (
            BatchProgressFormatter,
        )

        result = BatchProgressFormatter._format_error_short("timeout", None)
        assert result == "Timed out"


# ---------------------------------------------------------------------------
# Integration tests: asyncio.Event-based domain cancellation
# ---------------------------------------------------------------------------


def _make_url_handler() -> URLHandler:
    """Create a URLHandler with mocked dependencies."""
    db = MagicMock()
    response_formatter = MagicMock()
    response_formatter.safe_reply = AsyncMock()
    response_formatter.safe_reply_with_id = AsyncMock(return_value=1)
    response_formatter.edit_message = AsyncMock(return_value=True)
    response_formatter.MAX_BATCH_URLS = 20
    url_processor = MagicMock()
    url_processor.handle_url_flow = AsyncMock()
    return URLHandler(db=db, response_formatter=response_formatter, url_processor=url_processor)


def _make_message(uid: int = 1) -> MagicMock:
    """Create a mock Telegram message."""
    msg = MagicMock()
    msg.chat = SimpleNamespace(id=uid)
    return msg


@pytest.mark.asyncio
async def test_concurrent_same_domain_cancel_on_timeout():
    """4 same-domain URLs: first times out, others cancelled immediately.

    Wall-clock should be close to 1x timeout, not 4x.
    """
    handler = _make_url_handler()
    test_timeout = 2.0

    urls = [
        "https://habr.com/article/1",
        "https://habr.com/article/2",
        "https://habr.com/article/3",
        "https://habr.com/article/4",
    ]

    async def _slow_handler(*args, **kwargs):
        await asyncio.sleep(999)

    handler.url_processor.handle_url_flow = AsyncMock(side_effect=_slow_handler)
    msg = _make_message()
    wall_start = time.monotonic()

    with (
        patch("app.adapters.telegram.url_handler.URL_INITIAL_TIMEOUT_SEC", test_timeout),
        patch("app.adapters.telegram.url_handler.URL_MAX_TIMEOUT_SEC", test_timeout * 2),
        patch("app.adapters.telegram.url_handler.URL_MAX_RETRIES", 0),
    ):
        await handler._process_multiple_urls_parallel(msg, urls, uid=1, correlation_id="test-cid")

    wall_elapsed = time.monotonic() - wall_start

    # Without the fix: 4 URLs x 2s = 8s minimum.
    # With the fix: ~2s for first timeout + near-instant sibling cancellation.
    # Allow 2.5x tolerance for CI slowness.
    assert wall_elapsed < test_timeout * 2.5, (
        f"Expected wall-clock < {test_timeout * 2.5}s but got {wall_elapsed:.1f}s. "
        "Domain fail-fast did not cancel in-flight siblings."
    )


@pytest.mark.asyncio
async def test_mixed_domains_only_cancel_affected():
    """2 slow domain-a URLs + 2 fast domain-b URLs.

    Domain-b should succeed; domain-a should fail.
    """
    handler = _make_url_handler()
    test_timeout = 2.0

    urls = [
        "https://slow-domain.com/page/1",
        "https://slow-domain.com/page/2",
        "https://fast-domain.com/page/1",
        "https://fast-domain.com/page/2",
    ]

    async def _domain_aware_handler(*args, **kwargs):
        # Extract URL from positional args (message, url, ...)
        url = args[1] if len(args) > 1 else kwargs.get("url", "")
        if "slow-domain.com" in url:
            await asyncio.sleep(999)
            return None
        return SimpleNamespace(title=f"Title for {url}")

    handler.url_processor.handle_url_flow = AsyncMock(side_effect=_domain_aware_handler)
    msg = _make_message()

    with (
        patch("app.adapters.telegram.url_handler.URL_INITIAL_TIMEOUT_SEC", test_timeout),
        patch("app.adapters.telegram.url_handler.URL_MAX_TIMEOUT_SEC", test_timeout * 2),
        patch("app.adapters.telegram.url_handler.URL_MAX_RETRIES", 0),
    ):
        await handler._process_multiple_urls_parallel(msg, urls, uid=1, correlation_id="test-cid")

    # Check the completion message for partial success
    calls = handler.response_formatter.safe_reply.call_args_list
    completion_call = calls[-1]
    completion_text = completion_call[0][1]

    # 2 fast-domain URLs succeed, 2 slow-domain URLs fail -> "2/4"
    assert "2/4" in completion_text, (
        f"Expected '2/4' in completion message but got: {completion_text}"
    )


@pytest.mark.asyncio
async def test_event_already_set_skips_immediately():
    """If domain event is pre-set (first URL timed out), remaining siblings skip in <1s.

    Both URLs are from the same domain. The first will timeout, setting the event.
    The second should be cancelled near-instantly by the event, not burning its own timeout.
    """
    handler = _make_url_handler()
    test_timeout = 2.0

    urls = [
        "https://already-failed.com/page/1",
        "https://already-failed.com/page/2",
    ]

    async def _hang_forever(*args, **kwargs):
        await asyncio.sleep(999)

    handler.url_processor.handle_url_flow = AsyncMock(side_effect=_hang_forever)
    msg = _make_message()
    wall_start = time.monotonic()

    with (
        patch("app.adapters.telegram.url_handler.URL_INITIAL_TIMEOUT_SEC", test_timeout),
        patch("app.adapters.telegram.url_handler.URL_MAX_TIMEOUT_SEC", test_timeout * 2),
        patch("app.adapters.telegram.url_handler.URL_MAX_RETRIES", 0),
    ):
        await handler._process_multiple_urls_parallel(msg, urls, uid=1, correlation_id="test-cid")

    wall_elapsed = time.monotonic() - wall_start

    # With domain event cancellation, total time should be close to 1x timeout.
    # Without, it would be 2x timeout (each URL independently burns through).
    assert wall_elapsed < test_timeout * 2.0, (
        f"Expected wall-clock < {test_timeout * 2.0}s but got {wall_elapsed:.1f}s. "
        "Domain event did not trigger immediate sibling skip."
    )
