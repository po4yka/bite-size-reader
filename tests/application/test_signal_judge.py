"""Tests for bounded LLM-as-judge signal scoring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapter_models.llm.llm_models import LLMCallResult
from app.application.services.signal_judge import SignalJudgeService
from app.core.call_status import CallStatus


class _FakeLLM:
    provider_name = "fake"

    def __init__(self, response_text: str, *, cost_usd: float | None = 0.01) -> None:
        self.calls: list[dict] = []
        self._response_text = response_text
        self._cost_usd = cost_usd

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return LLMCallResult(
            status=CallStatus.OK,
            response_text=self._response_text,
            cost_usd=self._cost_usd,
            latency_ms=123,
            model="test-model",
        )


@pytest.mark.asyncio
async def test_signal_judge_calls_llm_only_for_capped_candidates() -> None:
    llm = _FakeLLM('{"relevance_score": 0.8, "decision": "queue", "reason": "useful"}')
    service = SignalJudgeService(llm_client=llm, daily_budget_usd=1.0)
    candidates = [
        SimpleNamespace(
            feed_item_id=1,
            should_reach_llm_judge=True,
            evidence={},
            score=0.7,
        ),
        SimpleNamespace(
            feed_item_id=2,
            should_reach_llm_judge=False,
            evidence={},
            score=0.4,
        ),
    ]
    rows = {
        1: {"title": "Useful post", "content_text": "body"},
        2: {"title": "Ignored post", "content_text": "body"},
    }

    judged = await service.judge(candidates, rows_by_item_id=rows)

    assert len(llm.calls) == 1
    assert judged[1].llm_score == 0.8
    assert judged[1].decision == "queue"
    assert 2 not in judged


@pytest.mark.asyncio
async def test_signal_judge_stops_at_daily_budget() -> None:
    llm = _FakeLLM('{"relevance_score": 0.8, "decision": "queue", "reason": "useful"}')
    service = SignalJudgeService(llm_client=llm, daily_budget_usd=0.0)
    candidates = [
        SimpleNamespace(feed_item_id=1, should_reach_llm_judge=True, evidence={}, score=0.7)
    ]

    judged = await service.judge(candidates, rows_by_item_id={1: {"title": "x"}})

    assert judged == {}
    assert llm.calls == []


@pytest.mark.asyncio
async def test_signal_judge_retries_invalid_json_once() -> None:
    class RetryLLM(_FakeLLM):
        async def chat(self, messages, **kwargs):
            self.calls.append({"messages": messages, **kwargs})
            text = "not json" if len(self.calls) == 1 else '{"relevance_score": 0.4, "decision": "skip", "reason": "weak"}'
            return LLMCallResult(status=CallStatus.OK, response_text=text, cost_usd=0.0)

    llm = RetryLLM("")
    service = SignalJudgeService(llm_client=llm, daily_budget_usd=1.0)

    judged = await service.judge(
        [SimpleNamespace(feed_item_id=1, should_reach_llm_judge=True, evidence={}, score=0.7)],
        rows_by_item_id={1: {"title": "x"}},
    )

    assert len(llm.calls) == 2
    assert judged[1].decision == "skip"
