import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("pydantic_settings", MagicMock())
sys.modules.setdefault("peewee", MagicMock())
sys.modules.setdefault("playhouse", MagicMock())
sys.modules.setdefault("playhouse.sqlite_ext", MagicMock())

from app.adapters.telegram.forward_summarizer import ForwardSummarizer  # noqa: E402


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

        db = MagicMock()
        openrouter = MagicMock()
        response_formatter = MagicMock()

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
