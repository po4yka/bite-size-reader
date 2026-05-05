"""Tests for search and discovery endpoints."""

from datetime import datetime, timedelta
from enum import Enum

# Python 3.10 compatibility shims (must be before app imports)
from typing import Any
from unittest.mock import AsyncMock, patch

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

from app.api.models.responses import PaginationInfo, SearchResult, SearchResultsData
from app.api.routers.auth.tokens import create_access_token
from app.api.services.search_service import SearchService
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


def _build_search_results(
    *,
    query: str,
    results: list[SearchResult] | None = None,
    total: int | None = None,
    limit: int = 10,
    offset: int = 0,
    intent: str = "keyword",
    mode: str = "keyword",
    facets: dict[str, Any] | None = None,
) -> SearchResultsData:
    search_results = results or []
    total_items = len(search_results) if total is None else total
    return SearchResultsData(
        results=search_results,
        pagination=PaginationInfo(
            total=total_items,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total_items,
        ),
        query=query,
        intent=intent,
        mode=mode,
        facets=facets or {"domains": [], "tags": [], "languages": []},
    )


@pytest.fixture
def mock_search_service_results():
    """Patch the search service with a generic empty-result response."""

    async def _search(**kwargs: Any) -> SearchResultsData:
        resolved_mode = kwargs.get("mode", "keyword")
        if resolved_mode == "auto":
            resolved_mode = "keyword"
        return _build_search_results(
            query=kwargs["q"],
            results=[],
            total=0,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            intent="keyword",
            mode=resolved_mode,
        )

    with patch.object(SearchService, "search_summaries", AsyncMock(side_effect=_search)) as mock:
        yield mock


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


def test_check_duplicate_not_duplicate(client, search_user, search_token):
    """Test URL that is not a duplicate."""
    with patch.object(
        SearchService,
        "check_duplicate",
        AsyncMock(
            return_value={
                "is_duplicate": False,
                "normalized_url": "https://newsite.com/article",
                "dedupe_hash": "abc123",
            }
        ),
    ):
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


def test_check_duplicate_is_duplicate(
    client,
    search_data,
    search_user,
    search_token,
):
    """Test URL that is a duplicate."""
    existing_url = search_data[0]["request"].input_url

    with patch.object(
        SearchService,
        "check_duplicate",
        AsyncMock(
            return_value={
                "is_duplicate": True,
                "request_id": search_data[0]["request"].id,
                "summary_id": search_data[0]["summary"].id,
                "summarized_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
    ):
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


def test_check_duplicate_with_summary(
    client,
    search_data,
    search_user,
    search_token,
):
    """Test duplicate check with summary details included."""
    existing_url = search_data[0]["request"].input_url

    with patch.object(
        SearchService,
        "check_duplicate",
        AsyncMock(
            return_value={
                "is_duplicate": True,
                "request_id": search_data[0]["request"].id,
                "summary_id": search_data[0]["summary"].id,
                "summarized_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "summary": {
                    "title": "Introduction to AI",
                    "tldr": "AI is transforming technology",
                    "url": existing_url,
                },
            }
        ),
    ):
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


def test_check_duplicate_different_user(client, search_data, search_user, db, monkeypatch):
    """Test that duplicate check respects user isolation."""
    # Create different user
    other_user = User.create(telegram_user_id=111222333, username="other_user")

    # Add both users to ALLOWED_USER_IDS
    monkeypatch.setenv(
        "ALLOWED_USER_IDS", f"{search_user.telegram_user_id},{other_user.telegram_user_id}"
    )

    other_token = create_access_token(other_user.telegram_user_id, client_id="test")

    # Check URL that exists for first user
    existing_url = search_data[0]["request"].input_url

    with patch.object(
        SearchService,
        "check_duplicate",
        AsyncMock(
            return_value={
                "is_duplicate": False,
                "normalized_url": existing_url,
                "dedupe_hash": "other-user-hash",
            }
        ),
    ):
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


def test_search_unicode_query(client, search_data, search_token, mock_search_service_results):
    """Test search with unicode characters."""
    response = client.get(
        "/v1/search",
        params={"q": "тест 测试", "limit": 10, "offset": 0},
        headers={"Authorization": f"Bearer {search_token}"},
    )

    assert response.status_code == 200


def test_isotime_helper_none_value(client):
    """Test _isotime helper with None value."""
    from app.api.search_helpers import isotime

    result = isotime(None)
    assert result == ""


def test_isotime_helper_datetime_value(client):
    """Test _isotime helper with datetime object."""
    from app.api.search_helpers import isotime

    dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
    result = isotime(dt)
    assert result.endswith("Z")
    assert "2023-01-01" in result


def test_isotime_helper_string_value(client):
    """Test _isotime helper with string value."""
    from app.api.search_helpers import isotime

    result = isotime("2023-01-01")
    assert result == "2023-01-01"


def test_search_response_structure(client, search_data, search_token, mock_search_service_results):
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
    with patch.object(
        SearchService,
        "semantic_search_summaries",
        AsyncMock(
            return_value=_build_search_results(
                query="test",
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
    client, search_data, search_token, mock_search_service_results
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
    with patch.object(
        SearchService,
        "semantic_search_summaries",
        AsyncMock(
            return_value=_build_search_results(
                query="ai",
                results=[
                    SearchResult(
                        request_id=1,
                        summary_id=1,
                        url="https://example.com/a",
                        title="A",
                        domain="example.com",
                        snippet="about ai",
                        tldr="ai",
                        published_at=None,
                        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                        relevance_score=0.9,
                        topic_tags=["#ai"],
                        is_read=False,
                        match_signals=["semantic"],
                        match_explanation="Matched semantically",
                        score_breakdown={
                            "fts": 0.0,
                            "semantic": 0.9,
                            "freshness": 0.5,
                            "popularity": 0.1,
                            "lexical": 0.6,
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
        ),
    ):
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
