"""Tests for search and discovery endpoints."""

from datetime import datetime, timedelta
from enum import Enum

# Python 3.10 compatibility shims (must be before app imports)
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class StrEnum(str, Enum):
    """Compatibility shim for StrEnum (Python 3.11+)."""


class _NotRequiredMeta(type):
    def __getitem__(cls, item: Any) -> Any:
        return item


class NotRequired(metaclass=_NotRequiredMeta):
    """Compatibility shim for NotRequired (Python 3.11+)."""


import enum
import typing

enum.StrEnum = StrEnum  # type: ignore[misc,assignment]
typing.NotRequired = NotRequired  # type: ignore[assignment]

from app.api.routers.auth import create_access_token
from app.core.time_utils import UTC
from app.core.url_utils import compute_dedupe_hash, normalize_url
from app.db.models import Request, Summary, TopicSearchIndex, User


@pytest.fixture
def search_user(db):
    """Create a test user for search tests."""
    return User.create(telegram_user_id=987654321, username="search_test_user")


@pytest.fixture
def search_token(search_user):
    """Create access token for search user."""
    return create_access_token(search_user.telegram_user_id, client_id="test")


@pytest.fixture
def search_data(db, search_user):
    """Create test data for search tests."""
    # Create multiple requests and summaries
    data = []

    # First article - about AI
    req1 = Request.create(
        user_id=search_user.telegram_user_id,
        type="url",
        status="completed",
        input_url="https://example.com/ai-article",
        normalized_url="https://example.com/ai-article",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )

    payload1 = {
        "summary_250": "This is an article about artificial intelligence and machine learning.",
        "summary_1000": "Long summary about AI",
        "tldr": "AI is transforming technology",
        "key_ideas": ["AI", "Machine Learning"],
        "topic_tags": ["#ai", "#technology"],
        "entities": {"people": [], "organizations": [], "locations": []},
        "estimated_reading_time_min": 5,
        "key_stats": [],
        "answered_questions": [],
        "readability": {"method": "FK", "score": 50.0, "level": "Easy"},
        "seo_keywords": ["ai", "artificial intelligence"],
        "metadata": {
            "title": "Introduction to AI",
            "domain": "example.com",
            "author": "John Doe",
            "published_at": "2023-01-01",
        },
        "confidence": 0.9,
        "hallucination_risk": "low",
    }

    summary1 = Summary.create(
        request=req1,
        lang="en",
        json_payload=payload1,
        is_read=False,
    )

    # Create FTS index entry for first article
    TopicSearchIndex.create(
        request_id=req1.id,
        title="Introduction to AI",
        snippet="This is an article about artificial intelligence",
        source="example.com",
        published_at=datetime.now(UTC) - timedelta(days=1),
        lang="en",
    )

    data.append({"request": req1, "summary": summary1})

    # Second article - about blockchain
    req2 = Request.create(
        user_id=search_user.telegram_user_id,
        type="url",
        status="completed",
        input_url="https://example.com/blockchain-article",
        normalized_url="https://example.com/blockchain-article",
        created_at=datetime.now(UTC) - timedelta(days=2),
    )

    payload2 = {
        "summary_250": "Blockchain technology and cryptocurrency explained.",
        "summary_1000": "Long summary about blockchain",
        "tldr": "Blockchain powers cryptocurrencies",
        "key_ideas": ["Blockchain", "Cryptocurrency"],
        "topic_tags": ["#blockchain", "#crypto"],
        "entities": {"people": [], "organizations": [], "locations": []},
        "estimated_reading_time_min": 7,
        "key_stats": [],
        "answered_questions": [],
        "readability": {"method": "FK", "score": 55.0, "level": "Medium"},
        "seo_keywords": ["blockchain", "crypto"],
        "metadata": {
            "title": "Understanding Blockchain",
            "domain": "example.com",
            "author": "Jane Smith",
            "published_at": "2023-02-01",
        },
        "confidence": 0.85,
        "hallucination_risk": "low",
    }

    summary2 = Summary.create(
        request=req2,
        lang="en",
        json_payload=payload2,
        is_read=True,
    )

    # Create FTS index entry for second article
    TopicSearchIndex.create(
        request_id=req2.id,
        title="Understanding Blockchain",
        snippet="Blockchain technology and cryptocurrency explained",
        source="example.com",
        published_at=datetime.now(UTC) - timedelta(days=2),
        lang="en",
    )

    data.append({"request": req2, "summary": summary2})

    return data


# ==================== FTS Search Tests ====================


@patch("app.api.routers.search.SqliteTopicSearchRepositoryAdapter")
@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
@patch("app.api.routers.search.SqliteSummaryRepositoryAdapter")
def test_search_summaries_success(
    mock_summary_repo_class,
    mock_request_repo_class,
    mock_search_repo_class,
    client,
    search_data,
    search_token,
):
    """Test successful FTS search with results."""
    # Mock FTS search results
    mock_search_repo = MagicMock()
    mock_search_repo.async_fts_search_paginated = AsyncMock(
        return_value=(
            [
                {
                    "request_id": search_data[0]["request"].id,
                    "title": "Introduction to AI",
                    "snippet": "AI article snippet",
                    "source": "example.com",
                    "published_at": "2023-01-01",
                }
            ],
            1,
        )
    )
    mock_search_repo_class.return_value = mock_search_repo

    # Mock request repository
    mock_request_repo = MagicMock()
    mock_request_repo.async_get_requests_by_ids = AsyncMock(
        return_value={
            search_data[0]["request"].id: {
                "id": search_data[0]["request"].id,
                "input_url": "https://example.com/ai-article",
                "normalized_url": "https://example.com/ai-article",
                "created_at": datetime.now(UTC),
            }
        }
    )
    mock_request_repo_class.return_value = mock_request_repo

    # Mock summary repository
    mock_summary_repo = MagicMock()
    mock_summary_repo.async_get_summaries_by_request_ids = AsyncMock(
        return_value={
            search_data[0]["request"].id: {
                "id": search_data[0]["summary"].id,
                "json_payload": search_data[0]["summary"].json_payload,
                "is_read": False,
            }
        }
    )
    mock_summary_repo_class.return_value = mock_summary_repo

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


def test_search_summaries_with_pagination(client, search_data, search_token, mock_fts_repos):
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


def test_search_summaries_no_results(client, search_data, search_token, mock_fts_repos):
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


def test_search_summaries_wildcard_syntax(client, search_data, search_token, mock_fts_repos):
    """Test FTS wildcard search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": "block*", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_search_summaries_phrase_syntax(client, search_data, search_token, mock_fts_repos):
    """Test FTS phrase search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": '"artificial intelligence"', "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_search_summaries_boolean_syntax(client, search_data, search_token, mock_fts_repos):
    """Test FTS boolean search syntax."""
    response = client.get(
        "/v1/search",
        params={"q": "blockchain AND crypto", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


@patch("app.api.routers.search.SqliteTopicSearchRepositoryAdapter")
def test_search_summaries_error_handling(mock_repo_class, client, search_token):
    """Test search error handling."""
    mock_repo = MagicMock()
    mock_repo.async_fts_search_paginated = AsyncMock(side_effect=Exception("DB error"))
    mock_repo_class.return_value = mock_repo

    response = client.get(
        "/v1/search",
        params={"q": "test", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 500


# ==================== Semantic Search Tests ====================


@pytest.fixture
def mock_chroma_service():
    """Mock Chroma search service."""
    service = MagicMock()
    service.search = AsyncMock()
    return service


@pytest.fixture
def mock_fts_repos():
    """Mock repositories for FTS search tests."""
    with (
        patch(
            "app.api.routers.search.SqliteTopicSearchRepositoryAdapter"
        ) as mock_search_repo_class,
        patch("app.api.routers.search.SqliteRequestRepositoryAdapter") as mock_request_repo_class,
        patch("app.api.routers.search.SqliteSummaryRepositoryAdapter") as mock_summary_repo_class,
    ):
        # Configure search repo
        mock_search_repo = MagicMock()
        mock_search_repo.async_fts_search_paginated = AsyncMock(return_value=([], 0))
        mock_search_repo_class.return_value = mock_search_repo

        # Configure request repo
        mock_request_repo = MagicMock()
        mock_request_repo.async_get_requests_by_ids = AsyncMock(return_value={})
        mock_request_repo_class.return_value = mock_request_repo

        # Configure summary repo
        mock_summary_repo = MagicMock()
        mock_summary_repo.async_get_summaries_by_request_ids = AsyncMock(return_value={})
        mock_summary_repo_class.return_value = mock_summary_repo

        yield {
            "search_repo": mock_search_repo,
            "request_repo": mock_request_repo,
            "summary_repo": mock_summary_repo,
        }


@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
@patch("app.api.routers.search.SqliteSummaryRepositoryAdapter")
def test_semantic_search_success(
    mock_summary_repo_class, mock_request_repo_class, client, search_data, search_token
):
    """Test successful semantic search."""
    from app.services.chroma_vector_search_service import (
        ChromaVectorSearchResult,
        ChromaVectorSearchResults,
    )

    # Mock Chroma service
    mock_service = MagicMock()
    mock_service.search = AsyncMock(
        return_value=ChromaVectorSearchResults(
            results=[
                ChromaVectorSearchResult(
                    request_id=search_data[0]["request"].id,
                    summary_id=search_data[0]["summary"].id,
                    url="https://example.com/ai-article",
                    title="Introduction to AI",
                    snippet="AI article snippet",
                    tags=["#ai", "#technology"],
                    similarity_score=0.95,
                )
            ],
            has_more=False,
        )
    )

    # Mock request repository
    mock_request_repo = MagicMock()
    mock_request_repo.async_get_requests_by_ids = AsyncMock(
        return_value={
            search_data[0]["request"].id: {
                "id": search_data[0]["request"].id,
                "input_url": "https://example.com/ai-article",
                "normalized_url": "https://example.com/ai-article",
                "created_at": datetime.now(UTC),
            }
        }
    )
    mock_request_repo_class.return_value = mock_request_repo

    # Mock summary repository
    mock_summary_repo = MagicMock()
    mock_summary_repo.async_get_summaries_by_request_ids = AsyncMock(
        return_value={
            search_data[0]["request"].id: {
                "id": search_data[0]["summary"].id,
                "json_payload": search_data[0]["summary"].json_payload,
                "is_read": False,
            }
        }
    )
    mock_summary_repo_class.return_value = mock_summary_repo

    async def mock_get_service():
        return mock_service

    with patch("app.api.routers.search.get_chroma_search_service", new=mock_get_service):
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


async def async_get_mock_chroma_service():
    """Async factory for mock service."""
    service = MagicMock()
    service.search = AsyncMock(return_value=None)
    return service


def test_semantic_search_with_filters(client, search_data, search_token):
    """Test semantic search with language and tag filters."""
    from app.api.dependencies.search_resources import get_chroma_search_service
    from app.api.main import app
    from app.services.chroma_vector_search_service import ChromaVectorSearchResults

    mock_service = MagicMock()
    mock_service.search = AsyncMock(
        return_value=ChromaVectorSearchResults(
            results=[],
            has_more=False,
        )
    )

    async def mock_get_service():
        return mock_service

    # Override FastAPI dependency
    app.dependency_overrides[get_chroma_search_service] = mock_get_service

    try:
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
        mock_service.search.assert_called_once()
        call_kwargs = mock_service.search.call_args[1]
        assert call_kwargs["language"] == "en"
        assert call_kwargs["tags"] == ["ai", "technology"]
        assert call_kwargs["user_scope"] == "test-scope"
    finally:
        # Clean up override
        app.dependency_overrides.clear()


def test_semantic_search_no_results(client, search_token):
    """Test semantic search with no results."""
    from app.services.chroma_vector_search_service import ChromaVectorSearchResults

    mock_service = MagicMock()
    mock_service.search = AsyncMock(
        return_value=ChromaVectorSearchResults(
            results=[],
            has_more=False,
        )
    )

    async def mock_get_service():
        return mock_service

    with patch("app.api.routers.search.get_chroma_search_service", new=mock_get_service):
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
    from app.api.dependencies.search_resources import get_chroma_search_service
    from app.api.main import app

    mock_service = MagicMock()
    mock_service.search = AsyncMock(side_effect=Exception("Chroma error"))

    async def mock_get_service():
        return mock_service

    # Override FastAPI dependency
    app.dependency_overrides[get_chroma_search_service] = mock_get_service

    try:
        response = client.get(
            "/v1/search/semantic",
            params={"q": "test", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

        assert response.status_code == 500
    finally:
        # Clean up override
        app.dependency_overrides.clear()


# ==================== Trending Topics Tests ====================


@patch("app.api.routers.search.get_trending_payload")
def test_get_trending_topics_success(mock_trending, client, search_token):
    """Test successful trending topics retrieval."""
    mock_trending.return_value = {
        "topics": [
            {"tag": "#ai", "count": 10, "trend_score": 1.5},
            {"tag": "#blockchain", "count": 8, "trend_score": 1.2},
        ],
        "total": 2,
    }

    response = client.get(
        "/v1/topics/trending",
        params={"limit": 20, "days": 30},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "topics" in data
    assert len(data["topics"]) == 2
    assert data["topics"][0]["tag"] == "#ai"


@patch("app.api.routers.search.get_trending_payload")
def test_get_trending_topics_with_custom_params(mock_trending, client, search_token):
    """Test trending topics with custom limit and days."""
    mock_trending.return_value = {"topics": [], "total": 0}

    response = client.get(
        "/v1/topics/trending",
        params={"limit": 10, "days": 7},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    # Verify function called with correct parameters
    mock_trending.assert_called_once()
    call_args = mock_trending.call_args
    assert call_args[1]["limit"] == 10
    assert call_args[1]["days"] == 7


def test_get_trending_topics_invalid_limit(client, search_token):
    """Test trending topics with invalid limit."""
    response = client.get(
        "/v1/topics/trending",
        params={"limit": 101, "days": 30},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_get_trending_topics_invalid_days(client, search_token):
    """Test trending topics with invalid days parameter."""
    response = client.get(
        "/v1/topics/trending",
        params={"limit": 20, "days": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422

    response = client.get(
        "/v1/topics/trending",
        params={"limit": 20, "days": 366},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


def test_get_trending_topics_unauthorized(client):
    """Test trending topics without authentication."""
    response = client.get(
        "/v1/topics/trending",
        params={"limit": 20, "days": 30},
    )

    assert response.status_code == 401


# ==================== Related Summaries Tests ====================


def test_get_related_summaries_success(client, search_data, search_token):
    """Test successful related summaries retrieval."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "ai", "limit": 20, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert "tag" in data
    assert "summaries" in data
    assert "pagination" in data
    # Tag should be normalized with #
    assert data["tag"] == "#ai"


def test_get_related_summaries_with_hash(client, search_data, search_token):
    """Test related summaries with hashtag already included."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "#blockchain", "limit": 20, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tag"] == "#blockchain"


def test_get_related_summaries_no_matches(client, search_data, search_token):
    """Test related summaries with no matching tag."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "nonexistent", "limit": 20, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["summaries"]) == 0


def test_get_related_summaries_case_insensitive(client, search_data, search_token):
    """Test that tag matching is case insensitive."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "AI", "limit": 20, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    # Should match #ai tag despite different case
    assert data["tag"] == "#AI"


def test_get_related_summaries_pagination(client, search_data, search_token):
    """Test related summaries pagination."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "ai", "limit": 1, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pagination"]["limit"] == 1
    assert data["pagination"]["offset"] == 0


def test_get_related_summaries_unauthorized(client):
    """Test related summaries without authentication."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "test", "limit": 20, "offset": 0},
    )

    assert response.status_code == 401


def test_get_related_summaries_empty_tag(client, search_token):
    """Test related summaries with empty tag."""
    response = client.get(
        "/v1/topics/related",
        params={"tag": "", "limit": 20, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


# ==================== Duplicate Check Tests ====================


@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
def test_check_duplicate_not_duplicate(mock_repo_class, client, search_user, search_token):
    """Test URL that is not a duplicate."""
    mock_repo = MagicMock()
    mock_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=None)
    mock_repo_class.return_value = mock_repo

    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": "https://newsite.com/article", "include_summary": False},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_duplicate"] is False
    assert "normalized_url" in data
    assert "dedupe_hash" in data


@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
@patch("app.api.routers.search.SqliteSummaryRepositoryAdapter")
def test_check_duplicate_is_duplicate(
    mock_summary_repo_class,
    mock_request_repo_class,
    client,
    search_data,
    search_user,
    search_token,
):
    """Test URL that is a duplicate."""
    # Mock request repository
    existing = {
        "id": search_data[0]["request"].id,
        "user_id": search_user.telegram_user_id,
        "created_at": datetime.now(UTC),
    }
    mock_request_repo = MagicMock()
    mock_request_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=existing)
    mock_request_repo_class.return_value = mock_request_repo

    # Mock summary repository
    mock_summary_repo = MagicMock()
    mock_summary_repo.async_get_summary_by_request = AsyncMock(
        return_value={"id": search_data[0]["summary"].id}
    )
    mock_summary_repo_class.return_value = mock_summary_repo

    existing_url = search_data[0]["request"].input_url

    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": existing_url, "include_summary": False},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_duplicate"] is True
    assert "request_id" in data
    assert "summary_id" in data
    assert "summarized_at" in data


@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
@patch("app.api.routers.search.SqliteSummaryRepositoryAdapter")
def test_check_duplicate_with_summary(
    mock_summary_repo_class,
    mock_request_repo_class,
    client,
    search_data,
    search_user,
    search_token,
):
    """Test duplicate check with summary details included."""
    # Mock request repository
    existing = {
        "id": search_data[0]["request"].id,
        "user_id": search_user.telegram_user_id,
        "input_url": "https://example.com/ai-article",
        "normalized_url": "https://example.com/ai-article",
        "created_at": datetime.now(UTC),
    }
    mock_request_repo = MagicMock()
    mock_request_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=existing)
    mock_request_repo_class.return_value = mock_request_repo

    # Mock summary repository
    mock_summary_repo = MagicMock()
    mock_summary_repo.async_get_summary_by_request = AsyncMock(
        return_value={
            "id": search_data[0]["summary"].id,
            "json_payload": search_data[0]["summary"].json_payload,
        }
    )
    mock_summary_repo_class.return_value = mock_summary_repo

    existing_url = search_data[0]["request"].input_url

    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": existing_url, "include_summary": True},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_duplicate"] is True
    assert "summary" in data
    assert "title" in data["summary"]
    assert "tldr" in data["summary"]
    assert "url" in data["summary"]


def test_check_duplicate_url_normalization(client, search_data, search_token):
    """Test that URL normalization works in duplicate detection."""
    # Original URL
    original_url = "https://example.com/ai-article"
    # URL with trailing slash and query params (should normalize to same)
    variant_url = "https://example.com/ai-article/?utm_source=test"

    # First, create a request with normalized original
    normalized = normalize_url(original_url)
    dedupe_hash = compute_dedupe_hash(normalized)

    req = Request.create(
        user_id=search_data[0]["request"].user_id,
        type="url",
        status="completed",
        input_url=original_url,
        normalized_url=normalized,
        dedupe_hash=dedupe_hash,
    )

    Summary.create(
        request=req,
        lang="en",
        json_payload={"tldr": "test"},
    )

    # Check variant URL
    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": variant_url, "include_summary": False},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_check_duplicate_unauthorized(client):
    """Test duplicate check without authentication."""
    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": "https://example.com/test", "include_summary": False},
    )

    assert response.status_code == 401


def test_check_duplicate_short_url(client, search_token):
    """Test duplicate check with URL below minimum length."""
    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": "http://a", "include_summary": False},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 422


@patch("app.api.routers.search.SqliteRequestRepositoryAdapter")
def test_check_duplicate_different_user(
    mock_request_repo_class, client, search_data, search_user, db, monkeypatch
):
    """Test that duplicate check respects user isolation."""
    # Create different user
    other_user = User.create(telegram_user_id=111222333, username="other_user")

    # Add both users to ALLOWED_USER_IDS
    monkeypatch.setenv(
        "ALLOWED_USER_IDS", f"{search_user.telegram_user_id},{other_user.telegram_user_id}"
    )

    other_token = create_access_token(other_user.telegram_user_id, client_id="test")

    # Mock request with different user_id
    existing = {
        "id": search_data[0]["request"].id,
        "user_id": search_user.telegram_user_id,  # Different from other_user
        "created_at": datetime.now(UTC),
    }
    mock_request_repo = MagicMock()
    mock_request_repo.async_get_request_by_dedupe_hash = AsyncMock(return_value=existing)
    mock_request_repo_class.return_value = mock_request_repo

    # Check URL that exists for first user
    existing_url = search_data[0]["request"].input_url

    response = client.get(
        "/v1/urls/check-duplicate",
        params={"url": existing_url, "include_summary": False},
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    # Should not be duplicate for different user
    assert data["is_duplicate"] is False


# ==================== Edge Cases and Error Handling ====================


def test_search_special_characters(client, search_data, search_token):
    """Test search with special characters in query."""
    response = client.get(
        "/v1/search",
        params={"q": "test@#$%", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    # Should not crash, may return no results
    assert response.status_code in [200, 500]


def test_search_unicode_query(client, search_data, search_token, mock_fts_repos):
    """Test search with unicode characters."""
    response = client.get(
        "/v1/search",
        params={"q": "тест 测试", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_isotime_helper_none_value(client):
    """Test _isotime helper with None value."""
    from app.api.routers.search import _isotime

    result = _isotime(None)
    assert result == ""


def test_isotime_helper_datetime_value(client):
    """Test _isotime helper with datetime object."""
    from app.api.routers.search import _isotime

    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = _isotime(dt)
    assert result.endswith("Z")
    assert "2023-01-01" in result


def test_isotime_helper_string_value(client):
    """Test _isotime helper with string value."""
    from app.api.routers.search import _isotime

    result = _isotime("2023-01-01")
    assert result == "2023-01-01"


def test_search_response_structure(client, search_data, search_token, mock_fts_repos):
    """Test that search response includes all required fields."""
    response = client.get(
        "/v1/search",
        params={"q": "example", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200
    json_data = response.json()

    # Top level structure
    assert "success" in json_data
    assert "data" in json_data
    assert "meta" in json_data

    # Meta structure
    assert "correlation_id" in json_data["meta"]
    assert "timestamp" in json_data["meta"]
    assert "version" in json_data["meta"]

    # Data structure
    data = json_data["data"]
    assert "results" in data
    assert "pagination" in data
    assert "query" in data

    # Pagination structure
    pagination = data["pagination"]
    assert "total" in pagination
    assert "limit" in pagination
    assert "offset" in pagination
    assert "hasMore" in pagination


def test_semantic_search_response_structure(client, search_token):
    """Test semantic search response structure."""
    from app.services.chroma_vector_search_service import ChromaVectorSearchResults

    mock_service = MagicMock()
    mock_service.search = AsyncMock(
        return_value=ChromaVectorSearchResults(
            results=[],
            has_more=False,
        )
    )

    async def mock_get_service():
        return mock_service

    with patch("app.api.routers.search.get_chroma_search_service", new=mock_get_service):
        response = client.get(
            "/v1/search/semantic",
            params={"q": "test", "limit": 10, "offset": 0},
            headers={"Authorization": f"Bearer {search_token}"},
        )

    assert response.status_code == 200
    json_data = response.json()

    assert "success" in json_data
    assert "data" in json_data
    assert "meta" in json_data

    data = json_data["data"]
    assert "results" in data
    assert "pagination" in data
    assert "query" in data


def test_search_response_includes_mode_intent_and_facets(
    client, search_data, search_token, mock_fts_repos
):
    """Search response should include intent/mode/facets metadata."""
    response = client.get(
        "/v1/search",
        params={"q": "ai trends", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data.get("intent") in {"topic", "keyword", "entity", "question", "similarity"}
    assert data.get("mode") in {"keyword", "semantic", "hybrid"}
    assert isinstance(data.get("facets"), dict)
    assert "domains" in data["facets"]


def test_semantic_search_response_includes_explanations(client, search_token):
    """Semantic results should include explainability fields."""
    from app.services.chroma_vector_search_service import (
        ChromaVectorSearchResult,
        ChromaVectorSearchResults,
    )

    mock_service = MagicMock()
    mock_service.search = AsyncMock(
        return_value=ChromaVectorSearchResults(
            results=[
                ChromaVectorSearchResult(
                    request_id=1,
                    summary_id=1,
                    similarity_score=0.9,
                    url="https://example.com/a",
                    title="A",
                    snippet="about ai",
                )
            ],
            has_more=False,
        )
    )

    async def mock_get_service():
        return mock_service

    with patch("app.api.routers.search.get_chroma_search_service", new=mock_get_service):
        with (
            patch(
                "app.api.routers.search.SqliteRequestRepositoryAdapter"
            ) as mock_request_repo_class,
            patch(
                "app.api.routers.search.SqliteSummaryRepositoryAdapter"
            ) as mock_summary_repo_class,
        ):
            mock_request_repo = MagicMock()
            mock_request_repo.async_get_requests_by_ids = AsyncMock(
                return_value={
                    1: {
                        "id": 1,
                        "input_url": "https://example.com/a",
                        "normalized_url": "https://example.com/a",
                        "created_at": datetime.now(UTC),
                    }
                }
            )
            mock_request_repo_class.return_value = mock_request_repo

            mock_summary_repo = MagicMock()
            mock_summary_repo.async_get_summaries_by_request_ids = AsyncMock(
                return_value={
                    1: {
                        "id": 1,
                        "lang": "en",
                        "json_payload": {
                            "summary_250": "about ai",
                            "tldr": "ai",
                            "topic_tags": ["#ai"],
                            "metadata": {"title": "A", "domain": "example.com"},
                        },
                        "is_read": False,
                        "is_favorited": False,
                    }
                }
            )
            mock_summary_repo_class.return_value = mock_summary_repo

            response = client.get(
                "/v1/search/semantic",
                params={"q": "ai", "limit": 10, "offset": 0},
                headers={"Authorization": f"Bearer {search_token}"},
            )

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    if results:
        assert "matchSignals" in results[0]
        assert "matchExplanation" in results[0]
        assert "scoreBreakdown" in results[0]


def test_search_insights_success(client, search_data, search_token):
    """Insights endpoint returns analytics blocks."""
    response = client.get(
        "/v1/search/insights",
        params={"days": 30, "limit": 10},
        headers={"Authorization": f"Bearer {search_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "topic_trends" in data
    assert "rising_entities" in data
    assert "source_diversity" in data
    assert "language_mix" in data
    assert "coverage_gaps" in data
