"""Tests for URLProcessor batch_mode and on_phase_change parameters."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.content.url_processor import URLProcessor

# Shared patch targets for module-level helpers
_PATCH_LANG = "app.adapters.content.url_processor.choose_language"
_PATCH_PROMPT = "app.adapters.content.url_processor._get_system_prompt"


class DummyChat:
    id = 123


class DummyMessage:
    def __init__(self) -> None:
        self.chat = DummyChat()


def _make_processor(
    *,
    content_extractor: Any = None,
    content_chunker: Any = None,
    llm_summarizer: Any = None,
    response_formatter: Any = None,
    summary_repo: Any = None,
    message_persistence: Any = None,
    cfg: Any = None,
) -> URLProcessor:
    """Create a URLProcessor with mocked dependencies via __new__ (skip __init__)."""
    proc = URLProcessor.__new__(URLProcessor)

    # Config
    if cfg is None:
        cfg = MagicMock()
        cfg.runtime.preferred_lang = "auto"
        cfg.openrouter.model = "test-model"
        cfg.openrouter.structured_output_mode = "json"
        cfg.openrouter.long_context_model = None
    proc.cfg = cfg

    # Content extractor
    if content_extractor is None:
        content_extractor = AsyncMock()
        content_extractor.extract_and_process_content = AsyncMock(
            return_value=(1, "Test content for the article.", "firecrawl", "en")
        )
    proc.content_extractor = content_extractor

    # Content chunker
    if content_chunker is None:
        content_chunker = MagicMock()
        content_chunker.should_chunk_content = MagicMock(return_value=(False, 10000, None))
    proc.content_chunker = content_chunker

    # LLM summarizer
    if llm_summarizer is None:
        llm_summarizer = AsyncMock()
        llm_summarizer.summarize_content = AsyncMock(
            return_value={"summary_250": "Test summary", "tldr": "Test tldr"}
        )
        llm_summarizer.last_llm_result = MagicMock(
            status="ok",
            latency_ms=100,
            model="test-model",
            cost_usd=0.01,
        )
    proc.llm_summarizer = llm_summarizer

    # Response formatter
    if response_formatter is None:
        response_formatter = AsyncMock()
    proc.response_formatter = response_formatter

    # Summary repo
    if summary_repo is None:
        summary_repo = AsyncMock()
    proc.summary_repo = summary_repo

    # Message persistence
    if message_persistence is None:
        message_persistence = MagicMock()
        message_persistence.request_repo = AsyncMock()
        message_persistence.request_repo.async_get_request_by_dedupe_hash = AsyncMock(
            return_value=None
        )
    proc.message_persistence = message_persistence

    # Audit function
    proc._audit = MagicMock()

    return proc


class TestBatchModeSuppressesNotifications(unittest.IsolatedAsyncioTestCase):
    """Verify that batch_mode=True suppresses all intermediate Telegram notifications."""

    async def test_batch_mode_skips_language_detection_notification(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-1",
                batch_mode=True,
            )

        assert result.success
        formatter.send_language_detection_notification.assert_not_called()

    async def test_batch_mode_skips_content_analysis_notification(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-2",
                batch_mode=True,
            )

        assert result.success
        formatter.send_content_analysis_notification.assert_not_called()

    async def test_batch_mode_skips_structured_summary_response(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-3",
                batch_mode=True,
            )

        assert result.success
        formatter.send_structured_summary_response.assert_not_called()

    async def test_batch_mode_skips_post_summary_tasks(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock) as mock_pst,
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-4",
                batch_mode=True,
            )

        assert result.success
        mock_pst.assert_not_called()

    async def test_batch_mode_skips_error_notification_on_summarization_failure(self) -> None:
        formatter = AsyncMock()
        summarizer = AsyncMock()
        summarizer.summarize_content = AsyncMock(return_value=None)
        summarizer.last_llm_result = None
        proc = _make_processor(response_formatter=formatter, llm_summarizer=summarizer)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-5",
                batch_mode=True,
            )

        assert not result.success
        formatter.send_error_notification.assert_not_called()

    async def test_batch_mode_skips_error_notification_on_exception(self) -> None:
        formatter = AsyncMock()
        extractor = AsyncMock()
        extractor.extract_and_process_content = AsyncMock(
            side_effect=RuntimeError("network failure")
        )
        proc = _make_processor(response_formatter=formatter, content_extractor=extractor)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-6",
                batch_mode=True,
            )

        assert not result.success
        formatter.send_error_notification.assert_not_called()


class TestNonBatchModeBackwardCompat(unittest.IsolatedAsyncioTestCase):
    """Verify that without batch_mode, all notifications are still sent (backward compat)."""

    async def test_default_mode_sends_language_detection_notification(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock),
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-bc-1",
            )

        assert result.success
        formatter.send_language_detection_notification.assert_called_once()

    async def test_default_mode_sends_content_analysis_notification(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock),
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-bc-2",
            )

        assert result.success
        formatter.send_content_analysis_notification.assert_called_once()

    async def test_default_mode_sends_structured_summary_response(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock),
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-bc-3",
            )

        assert result.success
        formatter.send_structured_summary_response.assert_called_once()

    async def test_default_mode_calls_post_summary_tasks(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock) as mock_pst,
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-bc-4",
            )

        assert result.success
        mock_pst.assert_called_once()

    async def test_default_mode_sends_error_notification_on_failure(self) -> None:
        formatter = AsyncMock()
        summarizer = AsyncMock()
        summarizer.summarize_content = AsyncMock(return_value=None)
        summarizer.last_llm_result = None
        proc = _make_processor(response_formatter=formatter, llm_summarizer=summarizer)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-bc-5",
            )

        assert not result.success
        formatter.send_error_notification.assert_called_once()


class TestOnPhaseChangeCallback(unittest.IsolatedAsyncioTestCase):
    """Verify on_phase_change callback is invoked at the right processing phases."""

    async def test_phase_change_called_for_extracting_and_analyzing(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)
        phases: list[str] = []

        async def track_phase(phase: str) -> None:
            phases.append(phase)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock),
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-phase-1",
                on_phase_change=track_phase,
            )

        assert result.success
        assert "extracting" in phases
        assert "analyzing" in phases
        # Extracting should come before analyzing
        assert phases.index("extracting") < phases.index("analyzing")

    async def test_phase_change_none_does_not_break(self) -> None:
        """on_phase_change=None (default) should not cause any errors."""
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
            patch.object(proc, "_schedule_post_summary_tasks", new_callable=AsyncMock),
        ):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-phase-2",
                on_phase_change=None,
            )

        assert result.success

    async def test_phase_change_works_with_batch_mode(self) -> None:
        """on_phase_change should still fire even in batch_mode."""
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)
        phases: list[str] = []

        async def track_phase(phase: str) -> None:
            phases.append(phase)

        with patch(_PATCH_LANG, return_value="en"), patch(_PATCH_PROMPT, return_value="prompt"):
            result = await proc.handle_url_flow(
                DummyMessage(),
                "https://example.com/article",
                correlation_id="cid-phase-3",
                batch_mode=True,
                on_phase_change=track_phase,
            )

        assert result.success
        assert "extracting" in phases
        assert "analyzing" in phases
