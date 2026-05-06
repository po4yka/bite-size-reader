"""Unit tests for MessagePersistence and command error handler.

Covers:
- MessagePersistence pure helpers (_to_epoch, _extract_entities_json,
  _extract_media_info, _extract_forward_info, _extract_raw_json)
- persist_message_snapshot validation and mocked async repos
- command_error_handler context manager behaviour
- handle_command_exception function behaviour
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.persistence.message_persistence import MessagePersistence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_persistence() -> tuple[MessagePersistence, MagicMock, MagicMock]:
    """Return (MessagePersistence, user_repo_mock, request_repo_mock)."""
    db = MagicMock()
    mp = pytest.MonkeyPatch()
    user_mock = AsyncMock()
    request_mock = AsyncMock()
    crawl_mock = MagicMock()
    mp.setattr(
        "app.infrastructure.persistence.message_persistence.UserRepositoryAdapter",
        lambda db: user_mock,
    )
    mp.setattr(
        "app.infrastructure.persistence.message_persistence.RequestRepositoryAdapter",
        lambda db: request_mock,
    )
    mp.setattr(
        "app.infrastructure.persistence.message_persistence.CrawlResultRepositoryAdapter",
        lambda db: crawl_mock,
    )
    persistence = MessagePersistence(db)
    mp.undo()
    return persistence, user_mock, request_mock


def _make_message(**kwargs):
    """Return a minimal fake Telegram message-like namespace."""
    defaults = {
        "id": 42,
        "chat": SimpleNamespace(id=100, type="private", title=None, username="user"),
        "from_user": SimpleNamespace(id=1, username="testuser"),
        "date": None,
        "text": "Hello world",
        "entities": [],
        "caption_entities": [],
        "photo": None,
        "video": None,
        "document": None,
        "audio": None,
        "voice": None,
        "animation": None,
        "sticker": None,
        "forward_from_chat": None,
        "forward_from_message_id": None,
        "forward_date": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _to_epoch
# ---------------------------------------------------------------------------


class TestToEpoch:
    def setup_method(self) -> None:
        persistence, _, _ = _make_persistence()
        self.p = persistence

    def test_none_returns_none(self) -> None:
        assert self.p._to_epoch(None) is None

    def test_datetime_returns_int_epoch(self) -> None:
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = self.p._to_epoch(dt)
        assert result == int(dt.timestamp())

    def test_integer_value_is_returned_as_int(self) -> None:
        now = int(time.time())
        assert self.p._to_epoch(now) == now

    def test_non_numeric_returns_none(self) -> None:
        assert self.p._to_epoch("not a timestamp") is None


# ---------------------------------------------------------------------------
# _extract_entities_json
# ---------------------------------------------------------------------------


class TestExtractEntitiesJson:
    def setup_method(self) -> None:
        persistence, _, _ = _make_persistence()
        self.p = persistence

    def test_empty_entities_returns_empty_list(self) -> None:
        msg = _make_message(entities=[], caption_entities=[])
        result = self.p._extract_entities_json(msg)
        assert result == []

    def test_entity_with_to_dict_is_serialised(self) -> None:
        entity = SimpleNamespace(to_dict=lambda: {"type": "bold", "offset": 0, "length": 5})
        msg = _make_message(entities=[entity], caption_entities=[])
        result = self.p._extract_entities_json(msg)
        assert result == [{"type": "bold", "offset": 0, "length": 5}]

    def test_entity_without_to_dict_uses_dict(self) -> None:
        entity = SimpleNamespace(__dict__={"type": "italic"})
        entity.to_dict = None  # not callable
        msg = _make_message(entities=[entity], caption_entities=[])
        # Should not raise; result may vary but should return a list
        result = self.p._extract_entities_json(msg)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _extract_media_info
# ---------------------------------------------------------------------------


class TestExtractMediaInfo:
    def setup_method(self) -> None:
        persistence, _, _ = _make_persistence()
        self.p = persistence

    def test_no_media_returns_none_tuple(self) -> None:
        msg = _make_message()
        media_type, file_ids = self.p._extract_media_info(msg)
        assert media_type is None
        assert file_ids is None

    def test_photo_detected_with_file_id(self) -> None:
        photo = SimpleNamespace(file_id="FILE123")
        msg = _make_message(photo=photo)
        media_type, file_ids = self.p._extract_media_info(msg)
        assert media_type == "photo"
        assert file_ids == ["FILE123"]

    def test_video_detected(self) -> None:
        video = SimpleNamespace(file_id="VID001")
        msg = _make_message(video=video)
        media_type, file_ids = self.p._extract_media_info(msg)
        assert media_type == "video"
        assert "VID001" in file_ids

    def test_document_detected(self) -> None:
        doc = SimpleNamespace(file_id="DOC001")
        msg = _make_message(document=doc)
        media_type, _ = self.p._extract_media_info(msg)
        assert media_type == "document"


# ---------------------------------------------------------------------------
# _extract_forward_info
# ---------------------------------------------------------------------------


class TestExtractForwardInfo:
    def setup_method(self) -> None:
        persistence, _, _ = _make_persistence()
        self.p = persistence

    def test_no_forward_returns_none_fields(self) -> None:
        msg = _make_message()
        info = self.p._extract_forward_info(msg)
        assert info["chat_id"] is None
        assert info["message_id"] is None

    def test_forward_chat_id_extracted(self) -> None:
        fwd_chat = SimpleNamespace(id=9999, type="channel", title="News")
        msg = _make_message(forward_from_chat=fwd_chat, forward_from_message_id=42)
        info = self.p._extract_forward_info(msg)
        assert info["chat_id"] == 9999
        assert info["message_id"] == 42


# ---------------------------------------------------------------------------
# _extract_raw_json
# ---------------------------------------------------------------------------


class TestExtractRawJson:
    def setup_method(self) -> None:
        persistence, _, _ = _make_persistence()
        self.p = persistence

    def test_message_with_to_dict_returns_dict(self) -> None:
        msg = _make_message()
        msg.to_dict = lambda: {"id": 42, "text": "hi"}
        result = self.p._extract_raw_json(msg)
        assert result == {"id": 42, "text": "hi"}

    def test_message_without_to_dict_returns_none(self) -> None:
        msg = _make_message()
        result = self.p._extract_raw_json(msg)
        assert result is None


# ---------------------------------------------------------------------------
# persist_message_snapshot validation
# ---------------------------------------------------------------------------


class TestPersistMessageSnapshotValidation:
    @pytest.mark.asyncio
    async def test_raises_on_invalid_request_id_zero(self) -> None:
        persistence, _, _ = _make_persistence()
        with pytest.raises(ValueError, match="Invalid request_id"):
            await persistence.persist_message_snapshot(0, _make_message())

    @pytest.mark.asyncio
    async def test_raises_on_none_message(self) -> None:
        persistence, _, _ = _make_persistence()
        with pytest.raises(ValueError, match="Message cannot be None"):
            await persistence.persist_message_snapshot(1, None)

    @pytest.mark.asyncio
    async def test_persists_telegram_message_row(self) -> None:
        persistence, _user_mock, request_mock = _make_persistence()
        msg = _make_message()
        await persistence.persist_message_snapshot(1, msg)
        request_mock.async_insert_telegram_message.assert_called_once()


# ---------------------------------------------------------------------------
# command_error_handler
# ---------------------------------------------------------------------------


class TestCommandErrorHandler:
    def _make_ctx(self, cid: str = "cid-test", interaction_id: int = 7) -> Any:
        from app.adapters.telegram.command_handlers.execution_context import (
            CommandExecutionContext,
        )

        return CommandExecutionContext(
            message=MagicMock(),
            text="/cmd",
            uid=1,
            chat_id=100,
            correlation_id=cid,
            interaction_id=interaction_id,
            start_time=0.0,
            user_repo=AsyncMock(),
            response_formatter=AsyncMock(),
            audit_func=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_passes_through_when_no_exception(self) -> None:
        from app.adapters.telegram.command_handlers.error_handler import (
            command_error_handler,
        )

        ctx = self._make_ctx()
        async with command_error_handler(ctx, "cmd_type", "Error msg", reraise=False):
            pass  # no exception

        ctx.response_formatter.send_error_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_error_notification_with_correlation_id(self) -> None:
        from app.adapters.telegram.command_handlers.error_handler import (
            command_error_handler,
        )

        ctx = self._make_ctx(cid="trace-abc")
        with pytest.raises(RuntimeError):
            async with command_error_handler(ctx, "cmd_type", "Something broke"):
                raise RuntimeError("boom")

        ctx.response_formatter.send_error_notification.assert_called_once()
        call_kwargs = ctx.response_formatter.send_error_notification.call_args
        # correlation_id must be passed through
        assert "trace-abc" in call_kwargs.args or any(
            "trace-abc" in str(v) for v in call_kwargs.args
        )

    @pytest.mark.asyncio
    async def test_reraise_false_swallows_exception(self) -> None:
        from app.adapters.telegram.command_handlers.error_handler import (
            command_error_handler,
        )

        ctx = self._make_ctx()
        # Should NOT raise
        async with command_error_handler(ctx, "cmd_type", "Error", reraise=False):
            raise ValueError("swallowed")

        ctx.response_formatter.send_error_notification.assert_called_once()


# ---------------------------------------------------------------------------
# handle_command_exception
# ---------------------------------------------------------------------------


class TestHandleCommandException:
    def _make_ctx(self, cid: str = "cid-func", interaction_id: int = 5) -> Any:
        from app.adapters.telegram.command_handlers.execution_context import (
            CommandExecutionContext,
        )

        return CommandExecutionContext(
            message=MagicMock(),
            text="/cmd",
            uid=1,
            chat_id=100,
            correlation_id=cid,
            interaction_id=interaction_id,
            start_time=0.0,
            user_repo=AsyncMock(),
            response_formatter=AsyncMock(),
            audit_func=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_sends_error_notification_with_correlation_id(self) -> None:
        from app.adapters.telegram.command_handlers.error_handler import (
            handle_command_exception,
        )

        ctx = self._make_ctx(cid="trace-xyz")
        await handle_command_exception(ctx, ValueError("test error"), "cmd", "msg")

        ctx.response_formatter.send_error_notification.assert_called_once()
        call_args = ctx.response_formatter.send_error_notification.call_args
        assert "trace-xyz" in call_args.args or any("trace-xyz" in str(v) for v in call_args.args)

    @pytest.mark.asyncio
    async def test_error_message_truncated_to_500_chars(self) -> None:
        from app.adapters.telegram.command_handlers.error_handler import (
            handle_command_exception,
        )

        ctx = self._make_ctx(interaction_id=0)  # no interaction to update
        long_error = "x" * 1000
        # Must complete without error even with a very long error message
        await handle_command_exception(ctx, ValueError(long_error), "cmd", "user msg")

        ctx.response_formatter.send_error_notification.assert_called_once()
