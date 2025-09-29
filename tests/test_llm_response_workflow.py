import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("pydantic_settings", MagicMock())
sys.modules.setdefault("peewee", MagicMock())
sys.modules.setdefault("playhouse", MagicMock())
sys.modules.setdefault("playhouse.sqlite_ext", MagicMock())

from app.adapters.content.llm_response_workflow import (  # noqa: E402
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)


class _DummySemaphore:
    async def __aenter__(self) -> None:  # noqa: D401 - simple semaphore
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - simple semaphore
        return None


class LLMResponseWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cfg = MagicMock()
        self.cfg.openrouter.model = "test-model"
        self.cfg.openrouter.fallback_models = ()
        self.cfg.openrouter.temperature = 0.1
        self.cfg.openrouter.top_p = 1.0
        self.cfg.openrouter.max_tokens = 4096
        self.cfg.openrouter.structured_output_mode = "json_object"

        self.db = MagicMock()
        self.db.async_upsert_summary = AsyncMock(return_value=1)
        self.db.async_update_request_status = AsyncMock()
        self.db.async_insert_llm_call = AsyncMock()

        self.response_formatter = MagicMock()
        self.openrouter = MagicMock()

        self.workflow = LLMResponseWorkflow(
            cfg=self.cfg,
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )

        self.base_messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Please summarise"},
        ]

        self.request = LLMRequestConfig(
            messages=self.base_messages,
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=0.1,
            top_p=1.0,
        )

        self.repair_context = LLMRepairContext(
            base_messages=self.base_messages,
            repair_response_format={"type": "json_object"},
            repair_max_tokens=256,
            default_prompt="Repair",
        )

        self.completion_mock = AsyncMock()
        self.llm_error_mock = AsyncMock()
        self.repair_failure_mock = AsyncMock()
        self.parsing_failure_mock = AsyncMock()

        self.notifications = LLMWorkflowNotifications(
            completion=self.completion_mock,
            llm_error=self.llm_error_mock,
            repair_failure=self.repair_failure_mock,
            parsing_failure=self.parsing_failure_mock,
        )

        self.interaction = LLMInteractionConfig(interaction_id=None)
        self.persistence = LLMSummaryPersistenceSettings(lang="en", is_read=True)

    async def test_execute_success_persists_summary(self) -> None:
        summary_payload = {
            "summary_250": "Summary body",
            "tldr": "TLDR text",
        }
        llm_response = self._llm_response(summary_payload)
        self.openrouter.chat = AsyncMock(return_value=llm_response)

        with unittest.mock.patch(
            "app.adapters.content.llm_response_workflow.parse_summary_response",
            return_value=SimpleNamespace(
                shaped={"summary_250": "Summary body", "tldr": "TLDR text"},
                errors=[],
                used_local_fix=False,
            ),
        ):
            summary = await self.workflow.execute_summary_workflow(
                message=MagicMock(),
                req_id=101,
                correlation_id="cid",
                interaction_config=self.interaction,
                persistence=self.persistence,
                repair_context=self.repair_context,
                requests=[self.request],
                notifications=self.notifications,
            )

        self.assertIsNotNone(summary)
        self.db.async_upsert_summary.assert_awaited_once()
        _args, kwargs = self.db.async_upsert_summary.await_args
        self.assertEqual(kwargs["request_id"], 101)
        self.assertEqual(kwargs["lang"], "en")
        self.db.async_update_request_status.assert_awaited_once_with(101, "ok")
        self.db.async_insert_llm_call.assert_awaited_once()
        self.completion_mock.assert_awaited_once()
        self.llm_error_mock.assert_not_awaited()

    async def test_execute_runs_repair_on_parse_failure(self) -> None:
        llm_invalid = self._llm_response({}, text="not json")
        llm_repaired = self._llm_response({}, text='{"summary_250": "Fixed", "tldr": "TLDR"}')
        self.openrouter.chat = AsyncMock(side_effect=[llm_invalid, llm_repaired])

        with unittest.mock.patch(
            "app.adapters.content.llm_response_workflow.parse_summary_response",
            side_effect=[
                SimpleNamespace(shaped=None, errors=["invalid"], used_local_fix=False),
                SimpleNamespace(
                    shaped={"summary_250": "Fixed", "tldr": "TLDR"},
                    errors=[],
                    used_local_fix=False,
                ),
            ],
        ):
            summary = await self.workflow.execute_summary_workflow(
                message=MagicMock(),
                req_id=202,
                correlation_id="repair",
                interaction_config=self.interaction,
                persistence=self.persistence,
                repair_context=self.repair_context,
                requests=[self.request],
                notifications=self.notifications,
            )

        self.assertIsNotNone(summary)
        self.assertEqual(self.openrouter.chat.await_count, 2)
        self.repair_failure_mock.assert_not_awaited()
        self.db.async_upsert_summary.assert_awaited_once()
        self.assertGreaterEqual(self.db.async_insert_llm_call.await_count, 1)

    async def test_execute_handles_llm_error(self) -> None:
        llm_error = self._llm_response({}, status="error", error_text="boom", text=None)
        self.openrouter.chat = AsyncMock(return_value=llm_error)

        summary = await self.workflow.execute_summary_workflow(
            message=MagicMock(),
            req_id=303,
            correlation_id="err",
            interaction_config=self.interaction,
            persistence=self.persistence,
            repair_context=self.repair_context,
            requests=[self.request],
            notifications=self.notifications,
        )

        self.assertIsNone(summary)
        self.db.async_upsert_summary.assert_not_awaited()
        self.db.async_update_request_status.assert_awaited_with(303, "error")
        self.db.async_insert_llm_call.assert_awaited_once()
        self.llm_error_mock.assert_awaited_once()

    def _llm_response(
        self,
        payload: dict[str, str],
        *,
        status: str = "ok",
        error_text: str | None = None,
        text: str | None = None,
    ) -> SimpleNamespace:
        response_text = text or self._to_json(payload)
        return SimpleNamespace(
            status=status,
            response_json=payload,
            response_text=response_text,
            model="test-model",
            endpoint="/chat",
            request_headers={},
            request_messages=self.base_messages,
            tokens_prompt=50,
            tokens_completion=25,
            cost_usd=0.01,
            latency_ms=120,
            error_text=error_text,
            structured_output_used=True,
            structured_output_mode="json_object",
            error_context=None,
        )

    @staticmethod
    def _to_json(payload: dict[str, str]) -> str:
        items = ", ".join(f'"{k}": "{v}"' for k, v in payload.items())
        return "{" + items + "}"
