from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.reranking_service import OpenRouterRerankingService, RerankingService


@pytest.mark.asyncio
async def test_reranking_service_returns_original_results_for_empty_inputs() -> None:
    service = RerankingService()
    results = [{"title": "A"}]

    assert await service.rerank("", results) == results
    assert await service.rerank("query", []) == []


@pytest.mark.asyncio
async def test_reranking_service_scores_and_sorts_top_k_results() -> None:
    service = RerankingService(top_k=2)
    service._score_pairs = AsyncMock(return_value=[0.1, 0.9])  # type: ignore[method-assign]
    results = [
        {"id": 1, "title": "First", "snippet": "low"},
        {"id": 2, "title": "Second", "snippet": "high"},
        {"id": 3, "title": "Tail", "snippet": "unchanged"},
    ]

    reranked = await service.rerank("query", results, id_field="id")

    assert [item["id"] for item in reranked] == [2, 1, 3]
    assert reranked[0]["rerank_score"] == 0.9
    assert reranked[1]["rerank_score"] == 0.1
    service._score_pairs.assert_awaited_once()


@pytest.mark.asyncio
async def test_reranking_service_falls_back_when_scoring_fails() -> None:
    service = RerankingService()
    service._score_pairs = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    results = [{"title": "First", "snippet": "snippet"}]

    assert await service.rerank("query", results) == results


@pytest.mark.asyncio
async def test_score_pairs_uses_model_predict_in_thread() -> None:
    service = RerankingService()
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.3, 0.7]
    service._ensure_model = MagicMock(return_value=fake_model)  # type: ignore[method-assign]

    scores = await service._score_pairs([["q", "a"], ["q", "b"]])

    assert scores == [0.3, 0.7]
    fake_model.predict.assert_called_once_with(
        [["q", "a"], ["q", "b"]],
        show_progress_bar=False,
    )


@pytest.mark.asyncio
async def test_openrouter_reranking_service_uses_structured_json_scores() -> None:
    client = MagicMock()
    client.chat = AsyncMock(
        return_value=SimpleNamespace(
            response_json={"results": [{"id": "b", "score": 0.8}, {"id": "a", "score": 0.2}]},
            response_text=None,
        )
    )
    service = OpenRouterRerankingService(client=client, top_k=2)
    results = [
        {"id": "a", "title": "Alpha", "text": "First"},
        {"id": "b", "title": "Beta", "text": "Second"},
        {"id": "c", "title": "Tail", "text": "Third"},
    ]

    reranked = await service.rerank("query", results, text_field="text")

    assert [item["id"] for item in reranked] == ["b", "a", "c"]
    assert reranked[0]["rerank_score"] == 0.8
    assert reranked[1]["rerank_score"] == 0.2
    client.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_openrouter_reranking_service_falls_back_when_chat_fails() -> None:
    client = MagicMock()
    client.chat = AsyncMock(side_effect=RuntimeError("llm unavailable"))
    service = OpenRouterRerankingService(client=client)
    results = [{"id": "a", "title": "Alpha", "text": "First"}]

    assert await service.rerank("query", results, text_field="text") == results


def test_extract_ranking_reads_json_and_text_payloads_and_handles_invalid_data() -> None:
    json_response = SimpleNamespace(
        response_json={"results": [{"id": "a", "score": 0.7}]}, response_text=None
    )
    text_response = SimpleNamespace(
        response_json=None, response_text='{"results":[{"id":"b","score":0.5}]}'
    )
    bad_response = SimpleNamespace(response_json=None, response_text="{broken")

    assert OpenRouterRerankingService._extract_ranking(json_response) == [{"id": "a", "score": 0.7}]
    assert OpenRouterRerankingService._extract_ranking(text_response) == [{"id": "b", "score": 0.5}]
    assert OpenRouterRerankingService._extract_ranking(bad_response) == []
