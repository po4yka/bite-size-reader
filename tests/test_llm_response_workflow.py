import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)

# NOTE: Do NOT mock peewee/playhouse at module level - it contaminates sys.modules
# and breaks tests that run after this one. The workflow tests use mocked
# repositories directly instead of mocking the ORM layer.


class _DummySemaphore:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
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
        # Mock runtime config timeouts used by semaphore/parsing wrappers
        self.cfg.runtime.semaphore_acquire_timeout_sec = 30.0
        self.cfg.runtime.llm_call_timeout_sec = 180.0
        self.cfg.runtime.json_parse_timeout_sec = 60.0

        self.db = MagicMock()
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

        # Mock repositories directly to avoid model/proxy issues
        # Store AsyncMock objects as typed instance variables for assertion access
        self.workflow.request_repo = MagicMock()
        self.update_status_mock: AsyncMock = AsyncMock()
        self.workflow.request_repo.async_update_request_status = self.update_status_mock

        self.workflow.summary_repo = MagicMock()
        self.upsert_summary_mock: AsyncMock = AsyncMock(return_value=1)
        self.workflow.summary_repo.async_upsert_summary = self.upsert_summary_mock

        self.workflow.llm_repo = MagicMock()
        self.insert_llm_call_mock: AsyncMock = AsyncMock(return_value=1)
        self.workflow.llm_repo.async_insert_llm_call = self.insert_llm_call_mock

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

        assert summary is not None
        self.upsert_summary_mock.assert_awaited_once()
        _args, kwargs = self.upsert_summary_mock.await_args
        assert kwargs["request_id"] == 101
        assert kwargs["lang"] == "en"
        self.update_status_mock.assert_awaited_once_with(101, "ok")
        self.insert_llm_call_mock.assert_awaited_once()
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

        assert summary is not None
        assert self.openrouter.chat.await_count == 2
        self.repair_failure_mock.assert_not_awaited()
        self.upsert_summary_mock.assert_awaited_once()
        assert self.insert_llm_call_mock.await_count >= 1

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

        assert summary is None
        self.upsert_summary_mock.assert_not_awaited()
        self.update_status_mock.assert_awaited_with(303, "error")
        self.insert_llm_call_mock.assert_awaited_once()
        # llm_error callback is called twice: once for the error, once for all attempts failed
        assert self.llm_error_mock.await_count == 2

    async def test_empty_summary_counts_attempts_and_models(self) -> None:
        req_primary = LLMRequestConfig(
            messages=self.base_messages,
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=0.1,
            top_p=1.0,
            model_override="primary",
        )
        req_fallback = LLMRequestConfig(
            messages=self.base_messages,
            response_format={"type": "json_object"},
            max_tokens=256,
            temperature=0.1,
            top_p=1.0,
            model_override="fallback",
        )

        llm_empty_first = self._llm_response({})
        llm_empty_second = self._llm_response({})
        self.openrouter.chat = AsyncMock(
            side_effect=[
                llm_empty_first,  # Primary request
                llm_empty_first,  # Primary repair
                llm_empty_second,  # Fallback request
                llm_empty_second,  # Fallback repair
            ]
        )

        with (
            unittest.mock.patch(
                "app.adapters.content.llm_response_workflow.parse_summary_response",
                return_value=SimpleNamespace(
                    shaped={}, errors=["missing_summary_fields"], used_local_fix=False
                ),
            ),
            unittest.mock.patch.object(
                self.workflow,
                "_handle_all_attempts_failed",
                wraps=self.workflow._handle_all_attempts_failed,
                new_callable=AsyncMock,
            ) as fail_mock,
        ):
            summary = await self.workflow.execute_summary_workflow(
                message=MagicMock(),
                req_id=404,
                correlation_id="empty",
                interaction_config=self.interaction,
                persistence=self.persistence,
                repair_context=self.repair_context,
                requests=[req_primary, req_fallback],
                notifications=self.notifications,
            )

        assert summary is None
        assert self.openrouter.chat.await_count == 4
        assert self.insert_llm_call_mock.await_count == 2
        fail_mock.assert_awaited_once()
        failed_attempts = fail_mock.await_args.args[5]
        assert len(failed_attempts) == 2
        models_tried = [cfg.model_override or llm.model for llm, cfg in failed_attempts]
        assert models_tried == ["primary", "fallback"]
        self.llm_error_mock.assert_awaited_once()
        _llm_arg, details = self.llm_error_mock.await_args.args
        assert "summary_fields_empty" in (details or "")

    async def test_process_attempt_exception_still_counts_attempt(self) -> None:
        llm_response = self._llm_response({})
        self.openrouter.chat = AsyncMock(return_value=llm_response)

        with (
            unittest.mock.patch.object(
                self.workflow,
                "_process_attempt",
                new_callable=AsyncMock,
                side_effect=ValueError("boom"),
            ),
            unittest.mock.patch.object(
                self.workflow,
                "_handle_all_attempts_failed",
                wraps=self.workflow._handle_all_attempts_failed,
                new_callable=AsyncMock,
            ) as fail_mock,
        ):
            summary = await self.workflow.execute_summary_workflow(
                message=MagicMock(),
                req_id=505,
                correlation_id="exception",
                interaction_config=self.interaction,
                persistence=self.persistence,
                repair_context=self.repair_context,
                requests=[self.request],
                notifications=self.notifications,
            )

        assert summary is None
        fail_mock.assert_awaited_once()
        failed_attempts = fail_mock.await_args.args[5]
        assert len(failed_attempts) == 1
        llm_logged, cfg_logged = failed_attempts[0]
        assert llm_logged.error_text == "summary_processing_exception"
        assert cfg_logged.preset_name == self.request.preset_name
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

    async def test_llm_call_timeout_fires_independently(self) -> None:
        """LLM call timeout fires even when semaphore is acquired quickly."""
        self.cfg.runtime.llm_call_timeout_sec = 0.05  # 50ms
        self.cfg.runtime.semaphore_acquire_timeout_sec = 30.0

        # Recreate workflow with updated config
        self.workflow = LLMResponseWorkflow(
            cfg=self.cfg,
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )

        async def slow_chat(*args, **kwargs):
            await asyncio.sleep(1.0)

        self.openrouter.chat = AsyncMock(side_effect=slow_chat)

        with self.assertRaises(TimeoutError):
            await self.workflow._invoke_llm(self.request, req_id=901)

    async def test_semaphore_timeout_fires_when_semaphore_blocked(self) -> None:
        """Semaphore timeout fires when the semaphore cannot be acquired in time."""
        self.cfg.runtime.semaphore_acquire_timeout_sec = 0.05  # 50ms
        self.cfg.runtime.llm_call_timeout_sec = 180.0

        class _BlockingSemaphore:
            async def __aenter__(self):
                await asyncio.sleep(1.0)

            async def __aexit__(self, *args):
                return None

        workflow = LLMResponseWorkflow(
            cfg=self.cfg,
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _BlockingSemaphore(),
        )

        self.openrouter.chat = AsyncMock(return_value=self._llm_response({"tldr": "ok"}))

        with self.assertRaises(TimeoutError):
            await workflow._invoke_llm(self.request, req_id=902)

    @staticmethod
    def _to_json(payload: dict[str, str]) -> str:
        items = ", ".join(f'"{k}": "{v}"' for k, v in payload.items())
        return "{" + items + "}"
