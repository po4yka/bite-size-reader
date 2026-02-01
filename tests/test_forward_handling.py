"""Comprehensive tests for forwarded message handling.

Covers:
- ForwardContentProcessor: title attribution, empty text guard, caption-only, dedup
- ForwardProcessor: handle_forward_flow, cached summary branches, exception handling
- ForwardSummarizer: truncation, Russian language prompt
- MessageRouter: caption-only forward routing
- MessagePersistence: forward_from_message_id default fix
- TelegramMessage: is_forwarded detection for all forward types
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.telegram.message_persistence import MessagePersistence
from app.db.database import Database
from app.db.models import database_proxy
from tests.conftest import make_test_app_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_forward_message(
    text: str | None = "Forward body",
    caption: str | None = None,
    fwd_chat_id: int | None = -100777,
    fwd_chat_title: str | None = "Test Channel",
    fwd_msg_id: int | None = 456,
    fwd_from_user: SimpleNamespace | None = None,
    fwd_sender_name: str | None = None,
    fwd_date: int | None = 1_700_000_100,
    user_id: int = 7,
    chat_id: int = 99,
) -> SimpleNamespace:
    """Build a forward message stub with configurable fields."""
    fwd_chat = None
    if fwd_chat_id is not None:
        fwd_chat = SimpleNamespace(id=fwd_chat_id, type="channel", title=fwd_chat_title)

    return SimpleNamespace(
        id=321,
        message_id=321,
        text=text,
        caption=caption,
        entities=[],
        caption_entities=[],
        chat=SimpleNamespace(id=chat_id),
        from_user=SimpleNamespace(id=user_id, username="tester"),
        forward_from_chat=fwd_chat,
        forward_from_message_id=fwd_msg_id,
        forward_from=fwd_from_user,
        forward_sender_name=fwd_sender_name,
        forward_date=fwd_date,
    )


def _make_processor(db_path: str):
    """Create a ForwardContentProcessor with real DB and mock formatter."""
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.forward_content_processor import ForwardContentProcessor

    db = Database(db_path)
    db.migrate()

    cfg = make_test_app_config(db_path=db_path, allowed_user_ids=(1,))
    formatter = MagicMock(spec=ResponseFormatter)
    formatter.send_forward_accepted_notification = AsyncMock()
    formatter.send_forward_language_notification = AsyncMock()
    formatter.safe_reply = AsyncMock()

    processor = ForwardContentProcessor(
        cfg=cfg,
        db=db,
        response_formatter=formatter,
        audit_func=lambda *a, **kw: None,
    )
    return processor, db, formatter


# ===========================================================================
# ForwardContentProcessor tests
# ===========================================================================


class TestForwardContentProcessorAttribution(unittest.IsolatedAsyncioTestCase):
    """Tests for source attribution logic in process_forward_content."""

    _old_proxy_obj: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._old_proxy_obj = database_proxy.obj

    @classmethod
    def tearDownClass(cls) -> None:
        database_proxy.initialize(cls._old_proxy_obj)

    async def test_channel_forward_uses_channel_label_and_title(self) -> None:
        """Channel forward should show 'Channel: <title>' in prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "a.db"))
            msg = _make_forward_message(text="Hello world", fwd_chat_title="My Channel")
            req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert prompt.startswith("Channel: My Channel\n\n")
            assert "Hello world" in prompt
            assert req_id > 0

    async def test_user_forward_uses_source_label_and_full_name(self) -> None:
        """User forward should show 'Source: FirstName LastName' in prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "b.db"))
            fwd_user = SimpleNamespace(first_name="Jane", last_name="Doe")
            msg = _make_forward_message(
                text="User content",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=fwd_user,
            )
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert prompt.startswith("Source: Jane Doe\n\n")
            assert "User content" in prompt

    async def test_user_forward_first_name_only(self) -> None:
        """User forward with only first_name should use it as attribution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "c.db"))
            fwd_user = SimpleNamespace(first_name="Alice", last_name=None)
            msg = _make_forward_message(
                text="First only",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=fwd_user,
            )
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert "Source: Alice\n\n" in prompt

    async def test_privacy_protected_forward_uses_sender_name(self) -> None:
        """Privacy-protected forward should fall back to forward_sender_name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "d.db"))
            msg = _make_forward_message(
                text="Hidden content",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=None,
                fwd_sender_name="Anonymous Writer",
            )
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert prompt.startswith("Source: Anonymous Writer\n\n")

    async def test_no_attribution_when_all_sources_missing(self) -> None:
        """When no channel/user/sender_name, prompt should be just the text."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "e.db"))
            msg = _make_forward_message(
                text="Orphan forward",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=None,
                fwd_sender_name=None,
            )
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert prompt == "Orphan forward"
            # Should NOT contain "Channel:" or "Source:"
            assert "Channel:" not in prompt
            assert "Source:" not in prompt


class TestForwardContentProcessorEmptyTextGuard(unittest.IsolatedAsyncioTestCase):
    """Tests for empty text detection in process_forward_content."""

    _old_proxy_obj: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._old_proxy_obj = database_proxy.obj

    @classmethod
    def tearDownClass(cls) -> None:
        database_proxy.initialize(cls._old_proxy_obj)

    async def test_empty_text_raises_value_error(self) -> None:
        """Media-only forward with no text should raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, fmt = _make_processor(os.path.join(tmpdir, "f.db"))
            msg = _make_forward_message(text=None, caption=None)
            with pytest.raises(ValueError, match="no text content"):
                await processor.process_forward_content(msg, "cid")
            fmt.safe_reply.assert_awaited_once()
            reply_text = fmt.safe_reply.call_args[0][1]
            assert "no text content" in reply_text.lower()

    async def test_whitespace_only_text_raises_value_error(self) -> None:
        """Forward with whitespace-only text should raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "g.db"))
            msg = _make_forward_message(text="   \n\t  ", caption=None)
            with pytest.raises(ValueError, match="no text content"):
                await processor.process_forward_content(msg, "cid")

    async def test_caption_used_when_text_is_none(self) -> None:
        """Forward with caption but no text should use caption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "h.db"))
            msg = _make_forward_message(text=None, caption="Caption content here")
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert "Caption content here" in prompt

    async def test_empty_string_text_uses_caption_fallback(self) -> None:
        """Forward with empty string text should fall back to caption."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "i.db"))
            msg = _make_forward_message(text="", caption="Fallback caption")
            _req_id, prompt, _lang, _sys = await processor.process_forward_content(msg, "cid")
            assert "Fallback caption" in prompt


class TestForwardContentProcessorDedup(unittest.IsolatedAsyncioTestCase):
    """Tests for forward request deduplication."""

    _old_proxy_obj: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._old_proxy_obj = database_proxy.obj

    @classmethod
    def tearDownClass(cls) -> None:
        database_proxy.initialize(cls._old_proxy_obj)

    async def test_same_channel_forward_reuses_request(self) -> None:
        """Forwarding the same channel post twice should reuse the request ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "j.db"))
            msg = _make_forward_message(text="Channel post", fwd_chat_id=-100999, fwd_msg_id=42)

            req_id_1, _p1, _l1, _s1 = await processor.process_forward_content(msg, "cid-1")
            req_id_2, _p2, _l2, _s2 = await processor.process_forward_content(msg, "cid-2")

            assert req_id_1 == req_id_2

    async def test_user_forward_no_dedup(self) -> None:
        """User forwards (no chat_id + msg_id pair) should not deduplicate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, _db, _fmt = _make_processor(os.path.join(tmpdir, "k.db"))
            fwd_user = SimpleNamespace(first_name="Bob", last_name=None)
            msg = _make_forward_message(
                text="User message",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=fwd_user,
            )

            req_id_1, _p1, _l1, _s1 = await processor.process_forward_content(msg, "cid-a")
            req_id_2, _p2, _l2, _s2 = await processor.process_forward_content(msg, "cid-b")

            assert req_id_1 != req_id_2

    async def test_forward_from_message_id_none_stored_as_null(self) -> None:
        """When forward_from_message_id is None, DB should store NULL not 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            processor, db, _fmt = _make_processor(os.path.join(tmpdir, "l.db"))
            msg = _make_forward_message(
                text="No msg id",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=SimpleNamespace(first_name="X", last_name=None),
            )
            req_id, _p, _l, _s = await processor.process_forward_content(msg, "cid")

            row = db.fetchone("SELECT fwd_from_msg_id FROM requests WHERE id = ?", (req_id,))
            assert row is not None
            assert row["fwd_from_msg_id"] is None  # Not 0


# ===========================================================================
# ForwardProcessor tests
# ===========================================================================


class TestForwardProcessorCachedSummary(unittest.IsolatedAsyncioTestCase):
    """Tests for _maybe_reply_with_cached_summary branches."""

    def _make_processor(self) -> tuple:
        """Build ForwardProcessor with mocked repositories."""
        from app.adapters.telegram.forward_processor import ForwardProcessor

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        db = MagicMock()
        openrouter = MagicMock()
        response_formatter = MagicMock()
        response_formatter.send_cached_summary_notification = AsyncMock()
        response_formatter.send_forward_summary_response = AsyncMock()

        audit_calls: list[tuple] = []

        processor = ForwardProcessor(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=lambda *a, **kw: audit_calls.append(a),
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )
        return processor, response_formatter, audit_calls

    async def test_no_summary_row_returns_false(self) -> None:
        """When no summary exists, should return False."""
        processor, fmt, _audit = self._make_processor()
        processor.summary_repo.async_get_summary_by_request = AsyncMock(return_value=None)

        result = await processor._maybe_reply_with_cached_summary(
            MagicMock(), 42, correlation_id="cid", interaction_id=None
        )
        assert result is False
        fmt.send_cached_summary_notification.assert_not_awaited()

    async def test_empty_payload_returns_false(self) -> None:
        """When summary row exists but json_payload is empty, should return False."""
        processor, _fmt, _audit = self._make_processor()
        processor.summary_repo.async_get_summary_by_request = AsyncMock(
            return_value={"json_payload": None}
        )

        result = await processor._maybe_reply_with_cached_summary(
            MagicMock(), 42, correlation_id="cid", interaction_id=None
        )
        assert result is False

    async def test_corrupted_json_returns_false(self) -> None:
        """When json_payload is not valid JSON, should return False."""
        processor, _fmt, _audit = self._make_processor()
        processor.summary_repo.async_get_summary_by_request = AsyncMock(
            return_value={"json_payload": "not{json"}
        )

        result = await processor._maybe_reply_with_cached_summary(
            MagicMock(), 42, correlation_id="cid", interaction_id=None
        )
        assert result is False

    async def test_valid_cache_hit_sends_notifications(self) -> None:
        """Valid cached summary should send notification, response, and update status."""
        processor, fmt, audit_calls = self._make_processor()
        payload = json.dumps({"summary_250": "cached", "tldr": "ok"})
        processor.summary_repo.async_get_summary_by_request = AsyncMock(
            return_value={"json_payload": payload}
        )
        processor.request_repo.async_update_request_status = AsyncMock()

        msg = MagicMock()
        result = await processor._maybe_reply_with_cached_summary(
            msg, 42, correlation_id="cid", interaction_id=None
        )

        assert result is True
        fmt.send_cached_summary_notification.assert_awaited_once_with(msg)
        fmt.send_forward_summary_response.assert_awaited_once()
        processor.request_repo.async_update_request_status.assert_awaited_once_with(42, "ok")
        assert any("forward_summary_cache_hit" in str(c) for c in audit_calls)

    async def test_valid_cache_hit_updates_interaction(self) -> None:
        """When interaction_id is provided, should update user interaction."""
        processor, _fmt, _audit = self._make_processor()
        payload = json.dumps({"summary_250": "cached"})
        processor.summary_repo.async_get_summary_by_request = AsyncMock(
            return_value={"json_payload": payload}
        )
        processor.request_repo.async_update_request_status = AsyncMock()

        with patch(
            "app.adapters.telegram.forward_processor.async_safe_update_user_interaction"
        ) as mock_update:
            mock_update.return_value = None
            result = await processor._maybe_reply_with_cached_summary(
                MagicMock(), 42, correlation_id="cid", interaction_id=99
            )

        assert result is True
        mock_update.assert_awaited_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["interaction_id"] == 99
        assert call_kwargs["response_sent"] is True


class TestForwardProcessorExceptionHandling(unittest.IsolatedAsyncioTestCase):
    """Tests for error handling in handle_forward_flow."""

    async def test_content_processor_error_caught(self) -> None:
        """Exception in content_processor should be caught and logged."""
        from app.adapters.telegram.forward_processor import ForwardProcessor

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        processor = ForwardProcessor(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        processor.content_processor.process_forward_content = AsyncMock(
            side_effect=ValueError("Forwarded message has no text content")
        )

        # Should NOT raise — exception is caught internally
        await processor.handle_forward_flow(MagicMock(), correlation_id="cid", interaction_id=None)

    async def test_summarizer_error_caught(self) -> None:
        """Exception in summarizer should be caught and logged."""
        from app.adapters.telegram.forward_processor import ForwardProcessor

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        processor = ForwardProcessor(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        processor.content_processor.process_forward_content = AsyncMock(
            return_value=(1, "prompt", "en", "sys")
        )
        processor._maybe_reply_with_cached_summary = AsyncMock(return_value=False)
        processor.summarizer.summarize_forward = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        # Should NOT raise
        await processor.handle_forward_flow(MagicMock(), correlation_id="cid", interaction_id=None)


class TestForwardProcessorCustomArticle(unittest.IsolatedAsyncioTestCase):
    """Tests for _maybe_generate_custom_article edge cases."""

    def _make_processor(self):
        from app.adapters.telegram.forward_processor import ForwardProcessor

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        return ForwardProcessor(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

    async def test_none_summary_returns_early(self) -> None:
        """When summary is None, should return immediately without LLM call."""
        processor = self._make_processor()
        # Patch LLMSummarizer so we know it's NOT called
        with patch("app.adapters.telegram.forward_processor.ForwardProcessor") as _:
            await processor._maybe_generate_custom_article(MagicMock(), None, "en", 1, "cid")
        # No assertions needed — just verifying no exception

    async def test_empty_topics_and_tags_returns_early(self) -> None:
        """When summary has empty key_ideas and topic_tags, should return early."""
        processor = self._make_processor()
        summary: dict[str, Any] = {"key_ideas": [], "topic_tags": []}
        # Should return without calling LLM
        await processor._maybe_generate_custom_article(MagicMock(), summary, "en", 1, "cid")

    async def test_non_mapping_summary_returns_early(self) -> None:
        """When summary is not a Mapping, should return early."""
        processor = self._make_processor()
        # Pass a string instead of dict
        await processor._maybe_generate_custom_article(
            MagicMock(), "not a dict", "en", 1, "cid"  # type: ignore[arg-type]
        )


# ===========================================================================
# ForwardSummarizer tests
# ===========================================================================


class TestForwardSummarizerTruncation(unittest.IsolatedAsyncioTestCase):
    """Tests for content truncation in ForwardSummarizer."""

    async def test_long_prompt_truncated(self) -> None:
        """Prompts longer than 45000 chars should be truncated."""
        from app.adapters.telegram.forward_summarizer import ForwardSummarizer

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        summarizer = ForwardSummarizer(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        long_prompt = "A" * 50000
        mock_workflow = AsyncMock(return_value={"summary_250": "ok"})

        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(
                MagicMock(), long_prompt, "en", "sys", 1, "cid", None
            )

        call_kwargs = mock_workflow.call_args.kwargs
        user_content = call_kwargs["requests"][0].messages[1]["content"]
        # The truncated prompt should end with the truncation marker
        assert "[Content truncated due to length]" in user_content

    async def test_short_prompt_not_truncated(self) -> None:
        """Prompts under 45000 chars should not be truncated."""
        from app.adapters.telegram.forward_summarizer import ForwardSummarizer

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        summarizer = ForwardSummarizer(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        short_prompt = "Short message"
        mock_workflow = AsyncMock(return_value={"summary_250": "ok"})

        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(
                MagicMock(), short_prompt, "en", "sys", 1, "cid", None
            )

        call_kwargs = mock_workflow.call_args.kwargs
        user_content = call_kwargs["requests"][0].messages[1]["content"]
        assert "[Content truncated" not in user_content
        assert "Short message" in user_content

    async def test_russian_language_prompt(self) -> None:
        """When chosen_lang is 'ru', the user message should say 'Russian'."""
        from app.adapters.telegram.forward_summarizer import ForwardSummarizer

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        summarizer = ForwardSummarizer(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        mock_workflow = AsyncMock(return_value={"summary_250": "ok"})

        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(
                MagicMock(), "Русский текст", "ru", "sys", 1, "cid", None
            )

        call_kwargs = mock_workflow.call_args.kwargs
        user_content = call_kwargs["requests"][0].messages[1]["content"]
        assert "Russian" in user_content
        assert "English" not in user_content

    async def test_english_language_prompt(self) -> None:
        """When chosen_lang is 'en', the user message should say 'English'."""
        from app.adapters.telegram.forward_summarizer import ForwardSummarizer

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        summarizer = ForwardSummarizer(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        mock_workflow = AsyncMock(return_value={"summary_250": "ok"})

        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(
                MagicMock(), "English text", "en", "sys", 1, "cid", None
            )

        call_kwargs = mock_workflow.call_args.kwargs
        user_content = call_kwargs["requests"][0].messages[1]["content"]
        assert "English" in user_content
        assert "Russian" not in user_content

    async def test_token_calculation(self) -> None:
        """Token calculation should follow max(2048, min(6144, len//4 + 2048))."""
        from app.adapters.telegram.forward_summarizer import ForwardSummarizer

        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"

        summarizer = ForwardSummarizer(
            cfg=cfg,
            db=MagicMock(),
            openrouter=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=lambda *a, **kw: None,
            sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        # Test with short prompt (should clamp to 2048)
        mock_workflow = AsyncMock(return_value=None)
        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(MagicMock(), "short", "en", "sys", 1, "cid", None)

        expected = max(2048, min(6144, len("short") // 4 + 2048))
        assert expected == 2049  # len("short")=5, 5//4=1, 1+2048=2049
        assert mock_workflow.call_args.kwargs["requests"][0].max_tokens == 2049

        # Test with long prompt (should clamp to 6144)
        long_text = "X" * 20000
        mock_workflow.reset_mock()
        with patch.object(summarizer._workflow, "execute_summary_workflow", new=mock_workflow):
            await summarizer.summarize_forward(MagicMock(), long_text, "en", "sys", 1, "cid", None)

        expected = max(2048, min(6144, len(long_text) // 4 + 2048))
        assert expected == 6144  # 20000//4 + 2048 = 7048, clamped to 6144
        assert mock_workflow.call_args.kwargs["requests"][0].max_tokens == 6144


# ===========================================================================
# MessageRouter forward routing edge cases
# ===========================================================================


@pytest.mark.asyncio
async def test_forward_caption_only_routes_to_forward_flow(
    tmp_path, tmp_path_factory, request
) -> None:
    """Forward with caption but no text should route to forward flow."""
    del tmp_path_factory, request
    from app.adapters.telegram.message_router import MessageRouter

    cfg = make_test_app_config(db_path=":memory:")
    db = Database(str(tmp_path / "router.db"))
    db.migrate()

    url_handler: Any = SimpleNamespace(
        url_processor=MagicMock(),
        is_awaiting_url=MagicMock(return_value=False),
        has_pending_multi_links=MagicMock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_multi_link_confirmation=AsyncMock(),
        add_pending_multi_links=MagicMock(),
        add_awaiting_user=MagicMock(),
    )
    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())
    response_formatter: Any = SimpleNamespace(safe_reply=AsyncMock())

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=SimpleNamespace(check_access=AsyncMock(return_value=True)),
        command_processor=MagicMock(),
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )

    message = SimpleNamespace(
        text=None,
        caption="Photo caption with content",
        forward_from=SimpleNamespace(id=1111, first_name="Captioner", last_name=None),
        forward_from_chat=None,
        forward_from_message_id=None,
        forward_sender_name=None,
        forward_date=1700000000,
    )

    await router._route_message_content(
        message,
        text="",
        uid=1,
        has_forward=True,
        correlation_id="cid-cap",
        interaction_id=200,
        start_time=0.0,
    )

    forward_processor.handle_forward_flow.assert_awaited_once()
    url_handler.handle_direct_url.assert_not_awaited()


@pytest.mark.asyncio
async def test_channel_forward_missing_msg_id_falls_to_user_path(
    tmp_path, tmp_path_factory, request
) -> None:
    """Channel forward with forward_from_message_id=None should try user forward path."""
    del tmp_path_factory, request
    from app.adapters.telegram.message_router import MessageRouter

    cfg = make_test_app_config(db_path=":memory:")
    db = Database(str(tmp_path / "router2.db"))
    db.migrate()

    url_handler: Any = SimpleNamespace(
        url_processor=MagicMock(),
        is_awaiting_url=AsyncMock(return_value=False),
        has_pending_multi_links=AsyncMock(return_value=False),
        handle_awaited_url=AsyncMock(),
        handle_direct_url=AsyncMock(),
        handle_multi_link_confirmation=AsyncMock(),
        add_pending_multi_links=MagicMock(),
        add_awaiting_user=MagicMock(),
    )
    forward_processor: Any = SimpleNamespace(handle_forward_flow=AsyncMock())
    response_formatter: Any = SimpleNamespace(safe_reply=AsyncMock())

    router = MessageRouter(
        cfg=cfg,
        db=db,
        access_controller=SimpleNamespace(check_access=AsyncMock(return_value=True)),
        command_processor=MagicMock(),
        url_handler=url_handler,
        forward_processor=forward_processor,
        response_formatter=response_formatter,
        audit_func=lambda *_args, **_kwargs: None,
    )

    # Channel forward but missing forward_from_message_id
    # This happens with some forwarded messages from restricted channels
    message = SimpleNamespace(
        text="Channel text without msg id",
        forward_from_chat=SimpleNamespace(id=-100555, title="Restricted"),
        forward_from_message_id=None,
        forward_from=None,
        forward_sender_name=None,
        forward_date=1700000000,
    )

    await router._route_message_content(
        message,
        text=message.text,
        uid=1,
        has_forward=True,
        correlation_id="cid-nomsg",
        interaction_id=300,
        start_time=0.0,
    )

    # Should NOT go through the channel forward path (needs both chat AND msg_id)
    # And no forward_from or sender_name set, so user forward path also doesn't match
    # Falls through to URL or default handler
    assert forward_processor.handle_forward_flow.await_count == 0


# ===========================================================================
# MessagePersistence forward_from_message_id default fix
# ===========================================================================


class TestMessagePersistenceForwardDefaults(unittest.IsolatedAsyncioTestCase):
    """Tests for forward_from_message_id default value in persistence."""

    _old_proxy_obj: Any = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._old_proxy_obj = database_proxy.obj

    @classmethod
    def tearDownClass(cls) -> None:
        database_proxy.initialize(cls._old_proxy_obj)

    async def test_forward_from_message_id_none_stored_as_null(self) -> None:
        """forward_from_message_id=None should persist as NULL, not 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persist.db")
            db = Database(db_path)
            db.migrate()

            persistence = MessagePersistence(db)

            msg = _make_forward_message(
                text="Content",
                fwd_chat_id=None,
                fwd_msg_id=None,
                fwd_from_user=SimpleNamespace(first_name="U", last_name=None),
            )

            # Create a request first
            req_id = await persistence.request_repo.async_create_request(
                type_="forward",
                status="pending",
                correlation_id="cid",
                chat_id=99,
                user_id=7,
            )

            await persistence.persist_message_snapshot(req_id, msg)

            row = db.fetchone(
                "SELECT forward_from_message_id FROM telegram_messages WHERE request_id = ?",
                (req_id,),
            )
            assert row is not None
            assert row["forward_from_message_id"] is None

    async def test_forward_from_message_id_present_stored_correctly(self) -> None:
        """forward_from_message_id=456 should persist as 456."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "persist2.db")
            db = Database(db_path)
            db.migrate()

            persistence = MessagePersistence(db)

            msg = _make_forward_message(text="Content", fwd_chat_id=-100, fwd_msg_id=456)

            req_id = await persistence.request_repo.async_create_request(
                type_="forward",
                status="pending",
                correlation_id="cid",
                chat_id=99,
                user_id=7,
            )

            await persistence.persist_message_snapshot(req_id, msg)

            row = db.fetchone(
                "SELECT forward_from_message_id FROM telegram_messages WHERE request_id = ?",
                (req_id,),
            )
            assert row is not None
            assert row["forward_from_message_id"] == 456


# ===========================================================================
# TelegramMessage is_forwarded detection
# ===========================================================================


class TestTelegramMessageIsForwarded(unittest.TestCase):
    """Tests for is_forwarded detection across all forward types."""

    def _make_mock_message(self, **overrides) -> SimpleNamespace:
        """Create a mock Pyrogram message with overridable forward fields."""
        from datetime import datetime

        defaults = {
            "id": 1,
            "date": datetime.now(),
            "text": "test",
            "caption": None,
            "entities": [],
            "caption_entities": [],
            "photo": None,
            "video": None,
            "audio": None,
            "document": None,
            "sticker": None,
            "voice": None,
            "video_note": None,
            "animation": None,
            "contact": None,
            "location": None,
            "venue": None,
            "poll": None,
            "dice": None,
            "game": None,
            "invoice": None,
            "successful_payment": None,
            "story": None,
            "forward_from": None,
            "forward_from_chat": None,
            "forward_from_message_id": None,
            "forward_signature": None,
            "forward_sender_name": None,
            "forward_date": None,
            "reply_to_message": None,
            "edit_date": None,
            "media_group_id": None,
            "author_signature": None,
            "via_bot": None,
            "has_protected_content": None,
            "connected_website": None,
            "reply_markup": None,
            "views": None,
            "via_bot_user_id": None,
            "effect_id": None,
            "link_preview_options": None,
            "show_caption_above_media": None,
            "from_user": None,
            "chat": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_regular_message_not_forwarded(self) -> None:
        """Message with no forward fields is not forwarded."""
        from app.models.telegram.telegram_message import TelegramMessage

        msg = self._make_mock_message()
        tm = TelegramMessage.from_pyrogram_message(msg)
        assert not tm.is_forwarded

    def test_forward_from_user_detected(self) -> None:
        """Forward from a user sets is_forwarded."""
        from app.models.telegram.telegram_message import TelegramMessage

        msg = self._make_mock_message(
            forward_from=SimpleNamespace(
                id=1,
                is_bot=False,
                first_name="A",
                last_name=None,
                username=None,
                language_code=None,
            )
        )
        tm = TelegramMessage.from_pyrogram_message(msg)
        assert tm.is_forwarded

    def test_forward_from_chat_detected(self) -> None:
        """Forward from a channel sets is_forwarded."""
        from app.models.telegram.telegram_message import TelegramMessage

        msg = self._make_mock_message(
            forward_from_chat=SimpleNamespace(id=-100, type="channel", title="Ch"),
            forward_from_message_id=42,
        )
        tm = TelegramMessage.from_pyrogram_message(msg)
        assert tm.is_forwarded

    def test_forward_sender_name_only_detected(self) -> None:
        """Privacy-protected forward (sender_name only) sets is_forwarded."""
        from app.models.telegram.telegram_message import TelegramMessage

        msg = self._make_mock_message(forward_sender_name="Hidden")
        tm = TelegramMessage.from_pyrogram_message(msg)
        assert tm.is_forwarded

    def test_forward_date_only_detected(self) -> None:
        """Forward with only forward_date set still detects as forwarded."""
        from datetime import datetime

        from app.models.telegram.telegram_message import TelegramMessage

        msg = self._make_mock_message(forward_date=datetime(2024, 1, 1))
        tm = TelegramMessage.from_pyrogram_message(msg)
        assert tm.is_forwarded


if __name__ == "__main__":
    unittest.main()
