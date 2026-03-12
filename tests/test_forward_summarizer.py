import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("pydantic_settings", MagicMock())
sys.modules.setdefault("peewee", MagicMock())
sys.modules.setdefault("playhouse", MagicMock())
sys.modules.setdefault("playhouse.sqlite_ext", MagicMock())

from app.adapters.telegram.forward_summarizer import ForwardSummarizer


class ForwardSummarizerTests(unittest.IsolatedAsyncioTestCase):
    class _Sem:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def test_summarize_forward_delegates_to_workflow(self) -> None:
        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"
        cfg.runtime.migration_worker_backend = "python"
        cfg.runtime.llm_provider = "openrouter"

        db = MagicMock()
        openrouter = MagicMock()
        response_formatter = MagicMock()
        response_formatter.send_forward_completion_notification = AsyncMock()
        response_formatter.send_error_notification = AsyncMock()

        summarizer = ForwardSummarizer(
            cfg,
            db,
            openrouter,
            response_formatter,
            lambda *a, **k: None,
            lambda: self._Sem(),
        )

        mock_workflow = AsyncMock(return_value={"summary_250": "ok", "tldr": "fine"})

        prompt = "Forward message"
        message = MagicMock()

        with patch.object(
            summarizer._workflow,
            "execute_summary_workflow",
            new=mock_workflow,
        ):
            result = await summarizer.summarize_forward(
                message=message,
                prompt=prompt,
                chosen_lang="en",
                system_prompt="sys",
                req_id=42,
                correlation_id="cid",
                interaction_id=99,
            )

        assert result == {"summary_250": "ok", "tldr": "fine"}
        mock_workflow.assert_awaited_once()

        call_kwargs = mock_workflow.call_args.kwargs
        requests = call_kwargs["requests"]
        assert len(requests) == 1
        expected_tokens = max(2048, min(6144, len(prompt) // 4 + 2048))
        assert requests[0].max_tokens == expected_tokens

        repair_context = call_kwargs["repair_context"]
        assert repair_context.repair_max_tokens == expected_tokens
        assert "Summarize the following" in repair_context.base_messages[1]["content"]

        notifications = call_kwargs["notifications"]
        assert notifications.completion is not None
        assert notifications.llm_error is not None

    async def test_summarize_forward_routes_to_rust_worker_when_enabled(self) -> None:
        cfg = MagicMock()
        cfg.openrouter.temperature = 0.2
        cfg.openrouter.top_p = 1.0
        cfg.openrouter.model = "primary"
        cfg.openrouter.fallback_models = ()
        cfg.openrouter.structured_output_mode = "json_object"
        cfg.runtime.migration_worker_backend = "rust"
        cfg.runtime.llm_provider = "openrouter"
        cfg.runtime.summary_streaming_enabled = False

        db = MagicMock()
        openrouter = MagicMock()
        response_formatter = MagicMock()
        response_formatter.send_forward_completion_notification = AsyncMock()
        response_formatter.send_error_notification = AsyncMock()

        summarizer = ForwardSummarizer(
            cfg,
            db,
            openrouter,
            response_formatter,
            lambda *a, **k: None,
            lambda: self._Sem(),
        )

        terminal_llm = MagicMock(status="ok", model="primary", error_text=None)
        persisted_attempts = [(terminal_llm, MagicMock())]

        with (
            patch.object(
                summarizer.worker_runner,
                "execute_forward_text",
                new=AsyncMock(
                    return_value={
                        "status": "ok",
                        "summary": {"summary_250": "ok", "summary_1000": "ok", "tldr": "fine"},
                        "attempts": [{}],
                        "terminal_attempt_index": 0,
                    }
                ),
            ),
            patch.object(
                summarizer,
                "_persist_worker_attempts",
                new=AsyncMock(return_value=persisted_attempts),
            ),
            patch.object(
                summarizer._workflow,
                "_finalize_success",
                new=AsyncMock(
                    return_value={"summary_250": "ok", "summary_1000": "ok", "tldr": "fine"}
                ),
            ) as finalize_success,
            patch.object(
                summarizer._workflow,
                "execute_summary_workflow",
                new=AsyncMock(),
            ) as workflow_exec,
        ):
            result = await summarizer.summarize_forward(
                message=MagicMock(),
                prompt="Forward message",
                chosen_lang="en",
                system_prompt="sys",
                req_id=42,
                correlation_id="cid-rust-worker",
                interaction_id=99,
            )

        assert result == {"summary_250": "ok", "summary_1000": "ok", "tldr": "fine"}
        finalize_success.assert_awaited_once()
        workflow_exec.assert_not_called()
