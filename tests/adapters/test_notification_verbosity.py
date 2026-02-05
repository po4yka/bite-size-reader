"""Tests for verbosity-aware notification formatting."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.adapters.external.formatting.notification_formatter import NotificationFormatterImpl
from app.core.progress_tracker import ProgressTracker
from app.core.verbosity import VerbosityLevel, VerbosityResolver


def _msg(uid: int = 1, chat_id: int = 100, msg_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid),
        chat=SimpleNamespace(id=chat_id),
        id=msg_id,
        message_id=msg_id,
    )


def _make_sender() -> MagicMock:
    sender = MagicMock()
    sender.safe_reply = AsyncMock()
    sender.safe_reply_with_id = AsyncMock(return_value=42)
    sender.edit_message = AsyncMock(return_value=True)
    sender.send_to_admin_log = AsyncMock()
    return sender


def _make_formatter(
    *, verbosity: VerbosityLevel | None = None
) -> tuple[NotificationFormatterImpl, MagicMock, ProgressTracker]:
    sender = _make_sender()
    data_fmt = MagicMock()
    data_fmt.format_firecrawl_options = MagicMock(return_value=None)

    resolver: VerbosityResolver | None = None
    if verbosity is not None:
        resolver = MagicMock(spec=VerbosityResolver)
        resolver.get_verbosity = AsyncMock(return_value=verbosity)

    tracker = ProgressTracker(sender)

    formatter = NotificationFormatterImpl(
        sender,
        data_fmt,
        verbosity_resolver=resolver,
        progress_tracker=tracker,
    )
    return formatter, sender, tracker


class TestNotificationVerbosityReader(unittest.IsolatedAsyncioTestCase):
    """In Reader mode, progress methods should use the tracker (edit-in-place)."""

    async def test_url_accepted_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_url_accepted_notification(_msg(), "https://example.com/article", "cid-1")

        # Should NOT send via safe_reply (debug); should use tracker
        sender.safe_reply.assert_not_awaited()
        sender.safe_reply_with_id.assert_awaited_once()
        # Admin log should still be called
        sender.send_to_admin_log.assert_awaited_once()

    async def test_firecrawl_start_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_firecrawl_start_notification(_msg(), "https://example.com")

        sender.safe_reply.assert_not_awaited()
        sender.safe_reply_with_id.assert_awaited_once()

    async def test_firecrawl_success_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_firecrawl_success_notification(_msg(), 5000, 12.3)

        sender.safe_reply.assert_not_awaited()

    async def test_llm_start_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_llm_start_notification(_msg(), "deepseek/v3", 5000, "json")

        sender.safe_reply.assert_not_awaited()

    async def test_llm_completion_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        llm = SimpleNamespace(
            status="ok",
            model="deepseek/v3",
            latency_ms=5000,
            tokens_prompt=100,
            tokens_completion=200,
            cost_usd=None,
            endpoint=None,
        )
        await fmt.send_llm_completion_notification(_msg(), llm, "cid-1")

        sender.safe_reply.assert_not_awaited()

    async def test_content_reuse_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_content_reuse_notification(_msg())

        sender.safe_reply.assert_not_awaited()

    async def test_html_fallback_uses_tracker(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_html_fallback_notification(_msg(), 10000)

        sender.safe_reply.assert_not_awaited()


class TestNotificationVerbosityDebug(unittest.IsolatedAsyncioTestCase):
    """In Debug mode, progress methods should use safe_reply (individual messages)."""

    async def test_url_accepted_uses_safe_reply(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.DEBUG)
        await fmt.send_url_accepted_notification(_msg(), "https://example.com/article", "cid-1")

        sender.safe_reply.assert_awaited_once()
        sender.safe_reply_with_id.assert_not_awaited()

    async def test_llm_start_uses_safe_reply(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.DEBUG)
        await fmt.send_llm_start_notification(_msg(), "deepseek/v3", 5000, "json")

        sender.safe_reply.assert_awaited_once()


class TestNotificationVerbosityNone(unittest.IsolatedAsyncioTestCase):
    """When no resolver is set (None), behaviour should match Debug (legacy)."""

    async def test_url_accepted_uses_safe_reply(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=None)
        await fmt.send_url_accepted_notification(_msg(), "https://example.com/article", "cid-1")

        sender.safe_reply.assert_awaited_once()

    async def test_error_always_shown(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_error_notification(_msg(), "generic", "cid-1", "something broke")

        sender.safe_reply.assert_awaited_once()

    async def test_silent_skips(self) -> None:
        fmt, sender, _ = _make_formatter(verbosity=VerbosityLevel.READER)
        await fmt.send_url_accepted_notification(
            _msg(), "https://example.com", "cid-1", silent=True
        )
        sender.safe_reply.assert_not_awaited()
        sender.safe_reply_with_id.assert_not_awaited()
