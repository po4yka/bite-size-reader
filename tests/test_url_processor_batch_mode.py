"""Tests for URLProcessor batch_mode and on_phase_change parameters."""

from __future__ import annotations

import unittest
from typing import Any, cast
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
        cfg.runtime.summary_prompt_version = "v1"
        cfg.runtime.summary_two_pass_enabled = False
        cfg.openrouter.model = "test-model"
        cfg.openrouter.structured_output_mode = "json"
        cfg.openrouter.long_context_model = None
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 0.9
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.flash_model = None
        cfg.openrouter.flash_fallback_models = ()
        cfg.openrouter.summary_temperature_json_fallback = None
        cfg.openrouter.summary_top_p_json_fallback = None
        cfg.attachment.vision_model = "vision-model"
    proc.cfg = cfg

    # Content extractor
    if content_extractor is None:
        content_extractor = AsyncMock()
        content_extractor.extract_and_process_content = AsyncMock(
            return_value=(1, "Test content for the article.", "firecrawl", "en", "Test Title", [])
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
    proc.processing_orchestrator = MagicMock(enabled=False)
    proc.processing_orchestrator.resolve_url_processing_plan = AsyncMock(
        return_value={
            "flow_kind": "url",
            "chosen_lang": "en",
            "needs_ru_translation": False,
            "summary_strategy": "single_pass",
            "effective_max_chars": 10000,
            "chunk_plan": None,
            "single_pass_request_plan": {"request_count": 2},
        }
    )

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

    async def test_rust_orchestrator_path_skips_python_hot_path_components(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)
        proc.processing_orchestrator = MagicMock(enabled=True)
        proc_any = cast("Any", proc)
        execute_url_flow = AsyncMock(
            return_value={
                "status": "ok",
                "request_id": 44,
                "summary_id": 11,
                "summary": {"summary_250": "Rust summary", "tldr": "Rust TLDR"},
                "chosen_lang": "en",
                "needs_ru_translation": False,
                "model": "rust-model",
                "chunk_count": 2,
                "dedupe_hash": "hash-44",
                "content_text": "Rust extracted content",
            }
        )
        maybe_reply_with_cached_summary = AsyncMock(side_effect=AssertionError("cache path"))
        extract_and_process_content = AsyncMock(side_effect=AssertionError("extractor path"))
        summarize_content = AsyncMock(side_effect=AssertionError("summarizer path"))
        schedule_post_summary_tasks = AsyncMock()
        proc.processing_orchestrator.execute_url_flow = execute_url_flow
        proc_any._maybe_reply_with_cached_summary = maybe_reply_with_cached_summary
        proc_any.content_extractor.extract_and_process_content = extract_and_process_content
        proc_any.llm_summarizer.summarize_content = summarize_content
        proc_any._schedule_post_summary_tasks = schedule_post_summary_tasks

        result = await proc.handle_url_flow(
            DummyMessage(),
            "https://example.com/article",
            correlation_id="cid-rust",
        )

        assert result.success
        execute_url_flow.assert_awaited_once()
        extract_and_process_content.assert_not_called()
        summarize_content.assert_not_called()
        formatter.send_structured_summary_response.assert_awaited_once()
        schedule_post_summary_tasks.assert_awaited_once()

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

        async def track_phase(
            phase: str,
            title: str | None = None,
            content_length: int | None = None,
            model: str | None = None,
        ) -> None:
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

        async def track_phase(
            phase: str,
            title: str | None = None,
            content_length: int | None = None,
            model: str | None = None,
        ) -> None:
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


class TestPipelineShadowHooks(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_context_uses_m3_rust_authoritative_resolvers(self) -> None:
        formatter = AsyncMock()
        proc = _make_processor(response_formatter=formatter)
        proc.pipeline_shadow = MagicMock()
        proc.pipeline_shadow.options.enabled = True
        proc.pipeline_shadow.resolve_extraction_adapter = AsyncMock(
            return_value={"language_hint": "en", "low_value": False}
        )
        proc.processing_orchestrator = MagicMock()
        proc.processing_orchestrator.resolve_url_processing_plan = AsyncMock(
            return_value={
                "flow_kind": "url",
                "chosen_lang": "en",
                "needs_ru_translation": False,
                "summary_strategy": "single_pass",
                "effective_max_chars": 10000,
                "chunk_plan": None,
                "single_pass_request_plan": {"request_count": 2},
            }
        )

        with (
            patch(_PATCH_LANG, return_value="en"),
            patch(_PATCH_PROMPT, return_value="prompt"),
        ):
            context = await proc._prepare_url_flow_context(
                message=DummyMessage(),
                url_text="https://example.com/article",
                correlation_id="cid-shadow",
                interaction_id=None,
                notify_silent=True,
                silent=True,
                batch_mode=True,
                on_phase_change=None,
                progress_tracker=None,
            )

        assert context.req_id == 1
        proc.pipeline_shadow.resolve_extraction_adapter.assert_called_once()
        proc.processing_orchestrator.resolve_url_processing_plan.assert_called_once()

    async def test_compute_chunk_strategy_uses_rust_chunk_sentence_plan(self) -> None:
        content_chunker = MagicMock()
        content_chunker.should_chunk_content = MagicMock(return_value=(False, 10000, None))
        proc = _make_processor(content_chunker=content_chunker)
        proc.pipeline_shadow = MagicMock()
        proc.pipeline_shadow.options.enabled = True
        proc.pipeline_shadow.resolve_chunking_preprocess = AsyncMock(
            return_value={
                "content_length": 220,
                "max_chars": 120,
                "chunk_size": 120,
                "should_chunk": True,
                "long_context_bypass": False,
                "estimated_chunk_count": 2,
                "first_chunk_size": 110,
            }
        )
        proc.pipeline_shadow.resolve_chunk_sentence_plan = AsyncMock(
            return_value={
                "lang": "en",
                "max_chars": 120,
                "chunk_size": 120,
                "sentences": ["A.", "B.", "C."],
                "chunks": ["A. B.", "C."],
                "chunk_count": 2,
                "first_chunk_size": 5,
            }
        )

        should_chunk, max_chars, chunks = await proc._compute_chunk_strategy(
            content_text="A. B. C.",
            chosen_lang="en",
            correlation_id="cid-shadow-chunk-plan",
            request_id=7,
        )

        assert should_chunk is True
        assert max_chars == 120
        assert chunks == ["A. B.", "C."]
        proc.pipeline_shadow.resolve_chunking_preprocess.assert_called_once()
        proc.pipeline_shadow.resolve_chunk_sentence_plan.assert_called_once_with(
            correlation_id="cid-shadow-chunk-plan",
            request_id=7,
            content_text="A. B. C.",
            lang="en",
            max_chars=120,
        )

    async def test_compute_chunk_strategy_disables_chunking_when_rust_chunks_empty(self) -> None:
        content_chunker = MagicMock()
        content_chunker.should_chunk_content = MagicMock(return_value=(False, 10000, None))
        proc = _make_processor(content_chunker=content_chunker)
        proc.pipeline_shadow = MagicMock()
        proc.pipeline_shadow.options.enabled = True
        proc.pipeline_shadow.resolve_chunking_preprocess = AsyncMock(
            return_value={
                "content_length": 220,
                "max_chars": 120,
                "chunk_size": 120,
                "should_chunk": True,
                "long_context_bypass": False,
                "estimated_chunk_count": 2,
                "first_chunk_size": 110,
            }
        )
        proc.pipeline_shadow.resolve_chunk_sentence_plan = AsyncMock(
            return_value={
                "lang": "en",
                "max_chars": 120,
                "chunk_size": 120,
                "sentences": ["A.", "B."],
                "chunks": ["", "   "],
                "chunk_count": 0,
                "first_chunk_size": 0,
            }
        )

        should_chunk, max_chars, chunks = await proc._compute_chunk_strategy(
            content_text="A. B.",
            chosen_lang="en",
            correlation_id="cid-shadow-empty-chunks",
            request_id=8,
        )

        assert should_chunk is False
        assert max_chars == 120
        assert chunks is None
