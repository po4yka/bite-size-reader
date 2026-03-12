import unittest
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.content.llm_summarizer import LLMSummarizer

if TYPE_CHECKING:
    from app.config import AppConfig


class _DummySemaphore:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class LLMSummarizerRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.cfg = SimpleNamespace(
            openrouter=SimpleNamespace(
                model="primary-model",
                fallback_models=("fallback-model",),
                temperature=0.2,
                top_p=0.9,
                max_tokens=None,
                long_context_model=None,
                summary_temperature_relaxed=None,
                summary_top_p_relaxed=None,
                summary_temperature_json_fallback=None,
                summary_top_p_json_fallback=None,
                enable_structured_outputs=True,
                structured_output_mode="json_schema",
                require_parameters=True,
                auto_fallback_structured=True,
            ),
            runtime=SimpleNamespace(summary_prompt_version="v1", summary_two_pass_enabled=False),
            web_search=SimpleNamespace(enabled=False),
            redis=SimpleNamespace(
                enabled=False,
                cache_enabled=False,
                prefix="",
                required=False,
                cache_timeout_sec=0.3,
                llm_ttl_seconds=7_200,
            ),
            attachment=SimpleNamespace(vision_model="vision-model"),
        )

        self.db = MagicMock()
        self.response_formatter = MagicMock()
        self.response_formatter.send_llm_completion_notification = AsyncMock()
        self.response_formatter.send_llm_start_notification = AsyncMock()
        self.response_formatter.send_error_notification = AsyncMock()
        self.response_formatter.send_cached_summary_notification = AsyncMock()
        self.openrouter = MagicMock()

    @patch("app.adapters.content.llm_summarizer.RedisCache")
    async def test_builds_parameter_presets_and_fallbacks(
        self, redis_cache_mock: MagicMock
    ) -> None:
        cache_stub = MagicMock()
        cache_stub.enabled = False
        cache_stub.get_json = AsyncMock(return_value=None)
        cache_stub.set_json = AsyncMock()
        redis_cache_mock.return_value = cache_stub

        summarizer = LLMSummarizer(
            cfg=cast("AppConfig", self.cfg),
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )

        captured_requests: list[Any] = []

        async def _capture_requests(**kwargs: Any):
            captured_requests.extend(kwargs.get("requests") or [])
            return {"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"}

        with patch.object(
            summarizer._workflow,
            "execute_summary_workflow",
            AsyncMock(side_effect=_capture_requests),
        ):
            summary = await summarizer.summarize_content(
                message=MagicMock(),
                content_text="short content for testing.",
                chosen_lang="en",
                system_prompt="system prompt",
                req_id=1,
                max_chars=10_000,
                correlation_id="cid",
            )

        assert summary is not None
        assert captured_requests, "requests should be built and passed to the workflow"
        preset_names = [req.preset_name for req in captured_requests]
        assert preset_names == [
            "schema_strict",
            "json_object_guardrail",
            "json_object_fallback",
        ]
        assert captured_requests[0].model_override == "primary-model"
        assert captured_requests[-1].model_override == "fallback-model"
        assert captured_requests[2].response_format.get("type") == "json_object"
        assert captured_requests[0].response_format.get("type") == "json_schema"

    @patch("app.adapters.content.llm_summarizer.RedisCache")
    async def test_uses_m3_rust_authoritative_llm_wrapper_plan(
        self, redis_cache_mock: MagicMock
    ) -> None:
        cache_stub = MagicMock()
        cache_stub.enabled = False
        cache_stub.get_json = AsyncMock(return_value=None)
        cache_stub.set_json = AsyncMock()
        redis_cache_mock.return_value = cache_stub

        summarizer = LLMSummarizer(
            cfg=cast("AppConfig", self.cfg),
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )
        summarizer.pipeline_shadow = MagicMock()
        summarizer.pipeline_shadow.options.enabled = True
        summarizer.pipeline_shadow.resolve_content_cleaner = AsyncMock(
            return_value={"content_text": "short content for testing."}
        )
        summarizer.pipeline_shadow.resolve_summary_user_content = AsyncMock(
            return_value={"user_content": "RUST USER CONTENT"}
        )
        summarizer.pipeline_shadow.resolve_llm_wrapper_plan = AsyncMock(
            return_value={
                "request_count": 3,
                "requests": [
                    {
                        "preset": "schema_strict",
                        "model": "primary-model",
                        "response_type": "json_schema",
                        "max_tokens": 4096,
                        "temperature": 0.2,
                        "top_p": 0.9,
                    },
                    {
                        "preset": "json_object_guardrail",
                        "model": "primary-model",
                        "response_type": "json_object",
                        "max_tokens": 4096,
                        "temperature": 0.15,
                        "top_p": 0.9,
                    },
                    {
                        "preset": "json_object_fallback",
                        "model": "fallback-model",
                        "response_type": "json_object",
                        "max_tokens": 4096,
                        "temperature": 0.15,
                        "top_p": 0.9,
                    },
                ],
            }
        )

        captured_requests: list[Any] = []

        async def _capture_requests(**kwargs: Any):
            captured_requests.extend(kwargs.get("requests") or [])
            return {"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"}

        with patch.object(
            summarizer._workflow,
            "execute_summary_workflow",
            AsyncMock(side_effect=_capture_requests),
        ):
            summary = await summarizer.summarize_content(
                message=MagicMock(),
                content_text="short content for testing.",
                chosen_lang="en",
                system_prompt="system prompt",
                req_id=7,
                max_chars=10_000,
                correlation_id="cid-shadow",
            )

        assert summary is not None
        summarizer.pipeline_shadow.resolve_content_cleaner.assert_called_once()
        summarizer.pipeline_shadow.resolve_summary_user_content.assert_called_once()
        summarizer.pipeline_shadow.resolve_llm_wrapper_plan.assert_called_once()
        assert captured_requests, "requests should be passed to the workflow"
        assert captured_requests[0].messages[1]["content"] == "RUST USER CONTENT"
        assert [req.preset_name for req in captured_requests] == [
            "schema_strict",
            "json_object_guardrail",
            "json_object_fallback",
        ]

    @patch("app.adapters.content.llm_summarizer.RedisCache")
    async def test_routes_single_pass_summary_to_rust_worker_when_enabled(
        self, redis_cache_mock: MagicMock
    ) -> None:
        cache_stub = MagicMock()
        cache_stub.enabled = False
        cache_stub.get_json = AsyncMock(return_value=None)
        cache_stub.set_json = AsyncMock()
        redis_cache_mock.return_value = cache_stub

        self.cfg.runtime.migration_worker_backend = "rust"

        summarizer = LLMSummarizer(
            cfg=cast("AppConfig", self.cfg),
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )

        with (
            patch(
                "app.adapters.content.llm_summarizer._execute_rust_worker_summary_for",
                new=AsyncMock(
                    return_value={"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"}
                ),
            ) as worker_exec,
            patch.object(
                summarizer._workflow,
                "execute_summary_workflow",
                new=AsyncMock(),
            ) as workflow_exec,
        ):
            summary = await summarizer.summarize_content(
                message=MagicMock(),
                content_text="short content for testing.",
                chosen_lang="en",
                system_prompt="system prompt",
                req_id=99,
                max_chars=10_000,
                correlation_id="cid-worker",
            )

        assert summary is not None
        worker_exec.assert_awaited_once()
        workflow_exec.assert_not_called()

    @patch("app.adapters.content.llm_summarizer.RedisCache")
    async def test_routes_multimodal_summary_to_rust_worker_when_enabled(
        self, redis_cache_mock: MagicMock
    ) -> None:
        cache_stub = MagicMock()
        cache_stub.enabled = False
        cache_stub.get_json = AsyncMock(return_value=None)
        cache_stub.set_json = AsyncMock()
        redis_cache_mock.return_value = cache_stub

        self.cfg.runtime.migration_worker_backend = "rust"

        summarizer = LLMSummarizer(
            cfg=cast("AppConfig", self.cfg),
            db=self.db,
            openrouter=self.openrouter,
            response_formatter=self.response_formatter,
            audit_func=lambda *args, **kwargs: None,
            sem=lambda: _DummySemaphore(),
        )

        with (
            patch(
                "app.adapters.content.llm_summarizer._execute_rust_worker_summary_for",
                new=AsyncMock(
                    return_value={"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"}
                ),
            ) as worker_exec,
            patch.object(
                summarizer._workflow,
                "execute_summary_workflow",
                new=AsyncMock(),
            ) as workflow_exec,
        ):
            summary = await summarizer.summarize_content(
                message=MagicMock(),
                content_text="short content for image testing.",
                chosen_lang="en",
                system_prompt="system prompt",
                req_id=101,
                max_chars=10_000,
                correlation_id="cid-worker-images",
                images=["https://example.test/one.png", "https://example.test/two.png"],
            )

        assert summary is not None
        worker_exec.assert_awaited_once()
        workflow_exec.assert_not_called()
        requests = worker_exec.await_args.kwargs["requests"]
        assert requests[0].model_override == "vision-model"
        user_content = requests[0].messages[1]["content"]
        assert isinstance(user_content, list)
        assert user_content[0] == {
            "type": "text",
            "text": requests[0].messages[1]["content"][0]["text"],
        }
        assert user_content[1] == {
            "type": "image_url",
            "image_url": {"url": "https://example.test/one.png"},
        }
        assert user_content[2] == {
            "type": "image_url",
            "image_url": {"url": "https://example.test/two.png"},
        }
