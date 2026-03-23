import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.content.pure_summary_service import PureSummaryService
from app.adapters.content.summarization_models import (
    EnsureSummaryPayloadRequest,
    PureSummaryRequest,
)
from app.adapters.content.summarization_runtime import SummarizationRuntime


def _dummy_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        openrouter=SimpleNamespace(
            model="primary-model",
            fallback_models=(),
            temperature=0.2,
            top_p=0.9,
            max_tokens=None,
            long_context_model=None,
            enable_structured_outputs=True,
            structured_output_mode="json_schema",
            require_parameters=True,
            auto_fallback_structured=True,
        ),
        runtime=SimpleNamespace(
            summary_prompt_version="v1",
            summary_two_pass_enabled=False,
        ),
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
        model_routing=SimpleNamespace(enabled=False, long_context_threshold=50000),
    )


def _ok_result(payload: dict[str, Any], *, model: str = "primary-model") -> SimpleNamespace:
    text = json.dumps(payload)
    return SimpleNamespace(
        status="ok",
        response_json={"choices": [{"message": {"content": text}}]},
        response_text=text,
        model=model,
        error_text=None,
    )


@pytest.mark.asyncio
@patch("app.adapters.content.summarization_runtime.RedisCache")
async def test_empty_content_rejected(redis_cache_mock: MagicMock) -> None:
    cache_stub = MagicMock(enabled=False)
    redis_cache_mock.return_value = cache_stub

    runtime = SummarizationRuntime(
        cfg=cast("Any", _dummy_cfg()),
        db=MagicMock(),
        openrouter=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=lambda *args, **kwargs: None,
        sem=lambda: MagicMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
    )
    service = PureSummaryService(runtime=runtime)

    with pytest.raises(ValueError, match="empty"):
        await service.summarize(
            PureSummaryRequest(
                content_text="   ",
                chosen_lang="en",
                system_prompt="prompt",
            )
        )


@pytest.mark.asyncio
@patch("app.adapters.content.summarization_runtime.RedisCache")
async def test_long_context_model_selected(redis_cache_mock: MagicMock) -> None:
    cache_stub = MagicMock(enabled=False)
    redis_cache_mock.return_value = cache_stub

    cfg = _dummy_cfg()
    cfg.openrouter.long_context_model = "long-model"
    openrouter = MagicMock()
    openrouter.chat = AsyncMock(
        return_value=_ok_result({"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"})
    )
    runtime = SummarizationRuntime(
        cfg=cast("Any", cfg),
        db=MagicMock(),
        openrouter=openrouter,
        response_formatter=MagicMock(),
        audit_func=lambda *args, **kwargs: None,
        sem=lambda: MagicMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock()),
    )
    service = PureSummaryService(runtime=runtime)

    await service.summarize(
        PureSummaryRequest(
            content_text="A" * 60000,
            chosen_lang="en",
            system_prompt="prompt",
            correlation_id="cid-long",
        )
    )

    assert openrouter.chat.await_args.kwargs["model_override"] == "long-model"


@pytest.mark.asyncio
@patch("app.adapters.content.summarization_runtime.RedisCache")
async def test_feedback_instructions_included(redis_cache_mock: MagicMock) -> None:
    cache_stub = MagicMock(enabled=False)
    redis_cache_mock.return_value = cache_stub

    openrouter = MagicMock()
    openrouter.chat = AsyncMock(
        return_value=_ok_result({"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"})
    )
    runtime = SummarizationRuntime(
        cfg=cast("Any", _dummy_cfg()),
        db=MagicMock(),
        openrouter=openrouter,
        response_formatter=MagicMock(),
        audit_func=lambda *args, **kwargs: None,
        sem=lambda: MagicMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock()),
    )
    service = PureSummaryService(runtime=runtime)

    await service.summarize(
        PureSummaryRequest(
            content_text="content",
            chosen_lang="en",
            system_prompt="prompt",
            correlation_id="cid-feedback",
            feedback_instructions="CORRECTIONS NEEDED FROM PREVIOUS ATTEMPT",
        )
    )

    user_message = openrouter.chat.await_args.args[0][1]["content"]
    assert "CORRECTIONS NEEDED FROM PREVIOUS ATTEMPT" in user_message


@pytest.mark.asyncio
@patch("app.adapters.content.summarization_runtime.RedisCache")
async def test_parse_failure_raises(redis_cache_mock: MagicMock) -> None:
    cache_stub = MagicMock(enabled=False)
    redis_cache_mock.return_value = cache_stub

    openrouter = MagicMock()
    openrouter.chat = AsyncMock(
        return_value=SimpleNamespace(
            status="ok",
            response_json={"choices": [{"message": {"content": "not json"}}]},
            response_text="not json",
            model="primary-model",
            error_text=None,
        )
    )
    runtime = SummarizationRuntime(
        cfg=cast("Any", _dummy_cfg()),
        db=MagicMock(),
        openrouter=openrouter,
        response_formatter=MagicMock(),
        audit_func=lambda *args, **kwargs: None,
        sem=lambda: MagicMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock()),
    )
    service = PureSummaryService(runtime=runtime)

    with pytest.raises(ValueError, match="parse"):
        await service.summarize(
            PureSummaryRequest(
                content_text="content",
                chosen_lang="en",
                system_prompt="prompt",
            )
        )


@pytest.mark.asyncio
@patch("app.adapters.content.summarization_runtime.RedisCache")
async def test_ensure_summary_payload_enriches_metadata(redis_cache_mock: MagicMock) -> None:
    cache_stub = MagicMock(enabled=False)
    redis_cache_mock.return_value = cache_stub

    runtime = SummarizationRuntime(
        cfg=cast("Any", _dummy_cfg()),
        db=MagicMock(),
        openrouter=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=lambda *args, **kwargs: None,
        sem=lambda: MagicMock(__aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock()),
    )
    ensure_summary_metadata = AsyncMock(
        return_value={"summary_250": "ok", "summary_1000": "ok", "tldr": "ok", "metadata": {}}
    )
    update_last_summary = MagicMock()
    cast("Any", runtime.metadata_helper).ensure_summary_metadata = ensure_summary_metadata
    cast("Any", runtime.insights_generator).update_last_summary = update_last_summary
    service = PureSummaryService(runtime=runtime)

    result = await service.ensure_summary_payload(
        EnsureSummaryPayloadRequest(
            summary={"summary_250": "ok", "summary_1000": "ok", "tldr": "ok"},
            req_id=1,
            content_text="content",
            chosen_lang="en",
            correlation_id="cid-meta",
        )
    )

    assert result["summary_250"] == "ok"
    ensure_summary_metadata.assert_awaited_once()
    update_last_summary.assert_called_once()
