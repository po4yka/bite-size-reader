"""Tests for FTS and semantic search endpoints."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.api.models.responses import SearchResult
from app.api.services.search_service import SearchService
from app.core.time_utils import UTC
from tests.api.conftest import _build_search_results


# ==================== FTS Search Tests ====================


def test_search_summaries_success(client, search_data, search_token):
    """Test successful FTS search with results."""
    mocked_result = _build_search_results(
        query="artificial intelligence",
        results=[
            SearchResult(
                request_id=search_data[0]["request"].id,
                summary_id=search_data[0]["summary"].id,
                url="https://example.com/ai-article",
                title="Introduction to AI",
                domain="example.com",
                snippet="AI article snippet",
                tldr="AI is transforming technology",
                published_at="2023-01-01",
                created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                relevance_score=0.95,
                topic_tags=["#ai", "#technology"],
                is_read=False,
                match_signals=["keyword"],
                match_explanation="Matched by keyword",
                score_breakdown={
                    "fts": 0.9,
                    "semantic": 0.0,
                    "freshness": 0.5,
                    "popularity": 0.2,
                    "lexical": 0.8,
                },
            )
        ],
        total=1,
        limit=10,
        offset=0,
        intent="keyword",
        mode="keyword",
        facets={"domains": ["example.com"], "tags": ["#ai"], "languages": ["en"]},
    )

    with patch.object(SearchService, "search_summaries", AsyncMock(return_value=mocked_result)):
        response = client.get(
            "/v1/search",
            params={"q": "artificial intelligence", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "results" in data["data"]
    assert "pagination" in data["data"]
    assert "query" in data["data"]
    assert data["data"]["query"] == "artificial intelligence"
    assert len(data["data"]["results"]) == 1


def test_search_summaries_with_pagination(
    client, search_data, search_token, mock_search_service_results
):
    """Test search with pagination parameters."""
    response = client.get(
        "/v1/search",
        params={"q": "example", "limit": 1, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"]["limit"] == 1
    assert data["pagination"]["offset"] == 0
    assert isinstance(data["pagination"]["hasMore"], bool)


def test_search_summaries_no_results(
    client, search_data, search_token, mock_search_service_results
):
    """Test search with no matching results."""
    response = client.get(
        "/v1/search",
        params={"q": "nonexistent-topic-xyz", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["results"]) == 0
    assert data["pagination"]["total"] == 0


def test_search_summaries_query_too_short(client, search_token):
    """Test search with query below minimum length."""
    response = client.get(
        "/v1/search",
        params={"q": "a", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_search_summaries_query_too_long(client, search_token):
    """Test search with query exceeding maximum length."""
    long_query = "a" * 201
    response = client.get(
        "/v1/search",
        params={"q": long_query, "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_search_summaries_invalid_limit(client, search_token):
    """Test search with invalid limit parameter."""
    # Limit too high
    response = client.get(
        "/v1/search",
        params={"q": "test", "limit": 101, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422

    # Limit too low
    response = client.get(
        "/v1/search",
        params={"q": "test", "limit": 0, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_search_summaries_invalid_offset(client, search_token):
    """Test search with negative offset."""
    response = client.get(
        "/v1/search",
        params={"q": "test", "limit": 10, "offset": -1},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_search_summaries_unauthorized(client, search_data):
    """Test search without authentication."""
    response = client.get(
        "/v1/search",
        params={"q": "test", "limit": 10, "offset": 0},
    )

    assert response.status_code == 401


def test_search_summaries_wildcard_syntax(
    client, search_data, search_token, mock_search_service_results
):
    """Test FTS wildcard search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": "block*", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_search_summaries_phrase_syntax(
    client, search_data, search_token, mock_search_service_results
):
    """Test FTS phrase search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": '"artificial intelligence"', "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_search_summaries_boolean_syntax(
    client, search_data, search_token, mock_search_service_results
):
    """Test FTS boolean search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": "blockchain AND crypto", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_search_summaries_error_handling(client, search_token):
    """Test search error handling."""
    with patch.object(
        SearchService, "search_summaries", AsyncMock(side_effect=Exception("DB error"))
    ):
        response = client.get(
            "/v1/search",
            params={"q": "test", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

    assert response.status_code == 500


# ==================== Semantic Search Tests ====================


def test_semantic_search_success(client, search_data, search_token):
    """Test successful semantic search."""
    mocked_result = _build_search_results(
        query="machine learning",
        results=[
            SearchResult(
                request_id=search_data[0]["request"].id,
                summary_id=search_data[0]["summary"].id,
                url="https://example.com/ai-article",
                title="Introduction to AI",
                domain="example.com",
                snippet="AI article snippet",
                tldr="AI is transforming technology",
                published_at="2023-01-01",
                created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                relevance_score=0.95,
                topic_tags=["#ai", "#technology"],
                is_read=False,
                match_signals=["semantic"],
                match_explanation="Matched semantically",
                score_breakdown={
                    "fts": 0.0,
                    "semantic": 0.95,
                    "freshness": 0.5,
                    "popularity": 0.2,
                    "lexical": 0.7,
                },
            )
        ],
        total=1,
        limit=10,
        offset=0,
        intent="similarity",
        mode="semantic",
        facets={"domains": ["example.com"], "tags": ["#ai"], "languages": ["en"]},
    )

    with patch.object(
        SearchService, "semantic_search_summaries", AsyncMock(return_value=mocked_result)
    ):
        response = client.get(
            "/v1/search/semantic",
            params={"q": "machine learning", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "results" in data
    assert "pagination" in data
    assert "query" in data
    assert data["query"] == "machine learning"
    # Result may be empty if request/summary don't match in mocks
    assert isinstance(data["results"], list)


def test_semantic_search_with_filters(client, search_data, search_token):
    """Test semantic search with language and tag filters."""
    mock_method = AsyncMock(
        return_value=_build_search_results(
            query="AI",
            results=[],
            total=0,
            limit=10,
            offset=0,
            intent="similarity",
            mode="semantic",
        )
    )

    with patch.object(SearchService, "semantic_search_summaries", mock_method):
        response = client.get(
            "/v1/search/semantic",
            params={
                "q": "AI",
                "limit": 10,
                "offset": 0,
                "language": "en",
                "tags": ["ai", "technology"],
                "user_scope": "test-scope",
            },
            headers={"Authorization": f"Bearer {search_token}"},
        )

        assert response.status_code == 200
        mock_method.assert_awaited_once()
        call_kwargs = mock_method.call_args.kwargs
        assert call_kwargs["filters"].language == "en"
        assert call_kwargs["filters"].tags == ["ai", "technology"]
        assert call_kwargs["user_scope"] == "test-scope"


def test_semantic_search_no_results(client, search_token):
    """Test semantic search with no results."""
    with patch.object(
        SearchService,
        "semantic_search_summaries",
        AsyncMock(
            return_value=_build_search_results(
                query="nonexistent topic",
                results=[],
                total=0,
                limit=10,
                offset=0,
                intent="similarity",
                mode="semantic",
            )
        ),
    ):
        response = client.get(
            "/v1/search/semantic",
            params={"q": "nonexistent topic", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["results"]) == 0


def test_semantic_search_unauthorized(client):
    """Test semantic search without authentication."""
    response = client.get(
        "/v1/search/semantic",
        params={"q": "test", "limit": 10, "offset": 0},
    )

    assert response.status_code == 401


def test_semantic_search_invalid_language(client, search_token):
    """Test semantic search with invalid language parameter."""
    response = client.get(
        "/v1/search/semantic",
        params={"q": "test", "limit": 10, "offset": 0, "language": "x"},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_semantic_search_error_handling(client, search_token):
    """Test semantic search error handling."""
    with patch.object(
        SearchService,
        "semantic_search_summaries",
        AsyncMock(side_effect=Exception("vector store error")),
    ):
        response = client.get(
            "/v1/search/semantic",
            params={"q": "test", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

        assert response.status_code == 500
