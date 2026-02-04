"""Tests for CancelledError propagation in notification and summary formatters."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock


class TestNotificationFormatterCancellation(unittest.IsolatedAsyncioTestCase):
    """Verify CancelledError is not swallowed by NotificationFormatterImpl."""

    def _make_formatter(self, *, safe_reply: AsyncMock | None = None):
        from app.adapters.external.formatting.notification_formatter import (
            NotificationFormatterImpl,
        )

        response_sender = MagicMock()
        response_sender.safe_reply = safe_reply or AsyncMock()
        data_formatter = MagicMock()
        data_formatter.format_firecrawl_options = MagicMock(return_value=None)
        return NotificationFormatterImpl(response_sender, data_formatter)

    async def test_send_url_accepted_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply must propagate out of send_url_accepted_notification."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        fmt = self._make_formatter(safe_reply=reply)

        with self.assertRaises(asyncio.CancelledError):
            await fmt.send_url_accepted_notification(MagicMock(), "https://example.com", "cid-123")

    async def test_send_firecrawl_start_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply must propagate out of send_firecrawl_start_notification."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        fmt = self._make_formatter(safe_reply=reply)

        with self.assertRaises(asyncio.CancelledError):
            await fmt.send_firecrawl_start_notification(MagicMock(), url="https://example.com")

    async def test_send_error_notification_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply must propagate out of send_error_notification."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        fmt = self._make_formatter(safe_reply=reply)

        with self.assertRaises(asyncio.CancelledError):
            await fmt.send_error_notification(
                MagicMock(), "firecrawl_error", "cid-456", details="timeout"
            )

    async def test_send_forward_accepted_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply must propagate out of send_forward_accepted_notification."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        fmt = self._make_formatter(safe_reply=reply)

        with self.assertRaises(asyncio.CancelledError):
            await fmt.send_forward_accepted_notification(MagicMock(), "Test Channel")

    async def test_regular_exception_still_swallowed(self) -> None:
        """Non-CancelledError exceptions should still be silently caught."""
        reply = AsyncMock(side_effect=RuntimeError("network"))
        fmt = self._make_formatter(safe_reply=reply)

        # Should not raise
        await fmt.send_url_accepted_notification(MagicMock(), "https://example.com", "cid-123")


class TestSummaryPresenterCancellation(unittest.IsolatedAsyncioTestCase):
    """Verify CancelledError is not swallowed by SummaryPresenterImpl."""

    def _make_presenter(self, *, safe_reply: AsyncMock | None = None):
        from app.adapters.external.formatting.summary_presenter import SummaryPresenterImpl

        response_sender = MagicMock()
        response_sender.safe_reply = safe_reply or AsyncMock()
        response_sender.reply_json = AsyncMock()
        text_processor = MagicMock()
        text_processor.sanitize_summary_text = MagicMock(side_effect=lambda x: x)
        text_processor.send_long_text = AsyncMock()
        text_processor.send_labelled_text = AsyncMock()
        data_formatter = MagicMock()
        data_formatter.format_key_stats = MagicMock(return_value=[])
        data_formatter.format_readability = MagicMock(return_value="")
        return SummaryPresenterImpl(response_sender, text_processor, data_formatter)

    async def test_send_structured_summary_header_propagates_cancelled_error(self) -> None:
        """CancelledError from the header safe_reply in send_structured_summary_response
        must propagate."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        presenter = self._make_presenter(safe_reply=reply)

        llm = MagicMock()
        llm.model = "test-model"

        summary = {"summary_250": "test"}

        with self.assertRaises(asyncio.CancelledError):
            await presenter.send_structured_summary_response(MagicMock(), summary, llm)

    async def test_send_forward_summary_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply in send_forward_summary_response must propagate."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        presenter = self._make_presenter(safe_reply=reply)

        forward_shaped = {"summary_250": "test forward"}

        with self.assertRaises(asyncio.CancelledError):
            await presenter.send_forward_summary_response(MagicMock(), forward_shaped)

    async def test_send_custom_article_propagates_cancelled_error(self) -> None:
        """CancelledError from safe_reply in send_custom_article must propagate."""
        reply = AsyncMock(side_effect=asyncio.CancelledError())
        presenter = self._make_presenter(safe_reply=reply)

        article = {"title": "Test", "article_markdown": "body", "highlights": []}

        with self.assertRaises(asyncio.CancelledError):
            await presenter.send_custom_article(MagicMock(), article)

    async def test_regular_exception_still_swallowed_in_forward(self) -> None:
        """Non-CancelledError exceptions should still be silently caught in forwards."""
        reply = AsyncMock(side_effect=RuntimeError("network"))
        presenter = self._make_presenter(safe_reply=reply)

        forward_shaped = {"summary_250": "test forward"}

        # Should not raise
        await presenter.send_forward_summary_response(MagicMock(), forward_shaped)


if __name__ == "__main__":
    unittest.main()
