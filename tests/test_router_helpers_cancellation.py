"""Tests that handle_document_file propagates asyncio.CancelledError from sleep calls."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

_DL_TARGET = "app.adapters.telegram.message_router_helpers.download_file"
_PARSE_TARGET = "app.adapters.telegram.message_router_helpers.parse_txt_file"
_SLEEP_TARGET = "app.adapters.telegram.message_router_helpers.asyncio.sleep"
_PROC_TARGET = "app.adapters.telegram.message_router_helpers.process_url_batch"


def _make_router() -> MagicMock:
    """Build a minimal mock router accepted by handle_document_file."""
    router = MagicMock()
    router.response_formatter.safe_reply = AsyncMock()
    router.response_formatter.safe_reply_with_id = AsyncMock(return_value=42)
    router.response_formatter.send_error_notification = AsyncMock()
    router.response_formatter.MIN_MESSAGE_INTERVAL_MS = 100
    router.response_formatter.MAX_BATCH_URLS = 50
    router.response_formatter._validate_url = MagicMock(return_value=(True, None))
    router._file_validator.cleanup_file = MagicMock()
    return router


class TestHandleDocumentFileCancellation(unittest.IsolatedAsyncioTestCase):
    """CancelledError from rate-limit sleeps must propagate, not be swallowed."""

    async def test_initial_sleep_propagates_cancelled_error(self) -> None:
        """CancelledError from the first asyncio.sleep (initial_gap) must propagate."""
        from app.adapters.telegram.message_router_helpers import handle_document_file

        router = _make_router()
        message = AsyncMock()

        with (
            patch(_DL_TARGET, new_callable=AsyncMock, return_value="/tmp/fake.txt"),
            patch(_PARSE_TARGET, return_value=["https://example.com"]),
            patch(_SLEEP_TARGET, side_effect=asyncio.CancelledError()),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await handle_document_file(router, message, "cid-test", 1, 0.0)

    async def test_post_processing_sleep_propagates_cancelled_error(self) -> None:
        """CancelledError from the second asyncio.sleep (min_gap_sec) must propagate."""
        from app.adapters.telegram.message_router_helpers import handle_document_file

        router = _make_router()
        message = AsyncMock()

        call_count = 0

        async def _selective_sleep(delay: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First sleep (initial_gap) succeeds
                return
            # Second sleep (min_gap_sec) cancelled
            raise asyncio.CancelledError()

        with (
            patch(_DL_TARGET, new_callable=AsyncMock, return_value="/tmp/fake.txt"),
            patch(_PARSE_TARGET, return_value=["https://example.com"]),
            patch(_PROC_TARGET, new_callable=AsyncMock),
            patch(_SLEEP_TARGET, side_effect=_selective_sleep),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await handle_document_file(router, message, "cid-test", 1, 0.0)

    async def test_regular_exceptions_still_handled(self) -> None:
        """Non-cancellation exceptions in sleep blocks should still be swallowed."""
        from app.adapters.telegram.message_router_helpers import handle_document_file

        router = _make_router()
        message = AsyncMock()

        with (
            patch(_DL_TARGET, new_callable=AsyncMock, return_value="/tmp/fake.txt"),
            patch(_PARSE_TARGET, return_value=["https://example.com"]),
            patch(_SLEEP_TARGET, side_effect=RuntimeError("timer glitch")),
        ):
            # Should NOT raise -- RuntimeError is still swallowed
            await handle_document_file(router, message, "cid-test", 1, 0.0)


if __name__ == "__main__":
    unittest.main()
