"""Regression tests for forward progress message consolidation."""

from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, MagicMock


class TestForwardProgressNotifications(unittest.IsolatedAsyncioTestCase):
    async def test_forward_notifications_edit_single_message_in_reader_mode(self) -> None:
        """Forward status updates should edit the same progress message, not create new ones."""
        from app.adapters.external.formatting.notification_formatter import (
            NotificationFormatterImpl,
        )
        from app.core.progress_tracker import ProgressTracker
        from app.core.verbosity import VerbosityLevel

        response_sender = MagicMock()
        response_sender.safe_reply = AsyncMock()
        response_sender.safe_reply_with_id = AsyncMock(return_value=123)
        response_sender.edit_message = AsyncMock(return_value=True)
        response_sender.send_to_admin_log = AsyncMock()

        verbosity_resolver = MagicMock()
        verbosity_resolver.get_verbosity = AsyncMock(return_value=VerbosityLevel.READER)

        progress_tracker = ProgressTracker(response_sender)
        data_formatter = MagicMock()

        fmt = NotificationFormatterImpl(
            response_sender,
            data_formatter,
            verbosity_resolver=verbosity_resolver,
            progress_tracker=progress_tracker,
        )

        message = types.SimpleNamespace(chat=types.SimpleNamespace(id=1), id=10)

        await fmt.send_forward_accepted_notification(message, "Test Channel")
        await fmt.send_forward_language_notification(message, "ru")

        response_sender.safe_reply_with_id.assert_awaited_once()
        response_sender.edit_message.assert_awaited_once_with(
            1,
            123,
            "Detected language: ru. Sending to model...",
            parse_mode=None,
            reply_markup=None,
            disable_web_page_preview=True,
        )
        response_sender.safe_reply.assert_not_awaited()
