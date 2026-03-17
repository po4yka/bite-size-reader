"""Tests for RelatedReadsService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.related_reads_service import (
    RelatedReadsService,
    _format_age,
)

# -- _format_age tests --


class TestFormatAge:
    def test_none_returns_empty(self) -> None:
        assert _format_age(None) == ""

    def test_invalid_string_returns_empty(self) -> None:
        assert _format_age("not-a-date") == ""

    def test_today(self) -> None:
        now = datetime.now(tz=timezone.utc)
        assert _format_age(now) == "today"

    def test_days(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=3)
        assert _format_age(dt) == "3d"

    def test_weeks(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(weeks=2)
        assert _format_age(dt) == "2w"

    def test_months(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=90)
        assert _format_age(dt) == "3mo"

    def test_years(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=400)
        assert _format_age(dt) == "1y"

    def test_string_iso_format(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=14)
        result = _format_age(dt.strftime("%Y-%m-%dT%H:%M:%S"))
        assert result == "2w"

    def test_string_date_only(self) -> None:
        dt = datetime.now(tz=timezone.utc) - timedelta(days=5)
        result = _format_age(dt.strftime("%Y-%m-%d"))
        assert result == "5d"


# -- RelatedReadsService tests --


def _make_vector_result(
    request_id: int = 1,
    summary_id: int = 10,
    similarity: float = 0.85,
    title: str = "Test Article",
    published_at: str | None = None,
) -> MagicMock:
    r = MagicMock()
    r.request_id = request_id
    r.summary_id = summary_id
    r.similarity_score = similarity
    r.title = title
    r.url = f"https://example.com/{request_id}"
    r.published_at = published_at
    return r


class TestRelatedReadsService:
    @pytest.fixture
    def vector_search(self) -> MagicMock:
        vs = MagicMock()
        vs.search = AsyncMock(return_value=[])
        return vs

    @pytest.fixture
    def service(self, vector_search: MagicMock) -> RelatedReadsService:
        return RelatedReadsService(vector_search, min_similarity=0.75, max_results=3)

    @pytest.mark.asyncio
    async def test_empty_payload_returns_empty(
        self, service: RelatedReadsService, vector_search: MagicMock
    ) -> None:
        result = await service.find_related({})
        assert result == []
        vector_search.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_finds_related(
        self, service: RelatedReadsService, vector_search: MagicMock
    ) -> None:
        vector_search.search.return_value = [
            _make_vector_result(request_id=1, similarity=0.9, title="Article A"),
            _make_vector_result(request_id=2, similarity=0.8, title="Article B"),
        ]
        payload = {"summary_250": "Some summary text", "tldr": "Short summary"}
        result = await service.find_related(payload)
        assert len(result) == 2
        assert result[0].title == "Article A"
        assert result[0].similarity_score == 0.9
        assert result[1].title == "Article B"

    @pytest.mark.asyncio
    async def test_excludes_current_request(
        self, service: RelatedReadsService, vector_search: MagicMock
    ) -> None:
        vector_search.search.return_value = [
            _make_vector_result(request_id=5, similarity=0.9),
            _make_vector_result(request_id=6, similarity=0.85),
        ]
        payload = {"summary_250": "Test content"}
        result = await service.find_related(payload, exclude_request_id=5)
        assert len(result) == 1
        assert result[0].request_id == 6

    @pytest.mark.asyncio
    async def test_filters_below_threshold(
        self, service: RelatedReadsService, vector_search: MagicMock
    ) -> None:
        vector_search.search.return_value = [
            _make_vector_result(request_id=1, similarity=0.9),
            _make_vector_result(request_id=2, similarity=0.5),  # below 0.75
        ]
        payload = {"summary_250": "Test content"}
        result = await service.find_related(payload)
        assert len(result) == 1
        assert result[0].request_id == 1

    @pytest.mark.asyncio
    async def test_respects_max_results(self, vector_search: MagicMock) -> None:
        svc = RelatedReadsService(vector_search, min_similarity=0.5, max_results=2)
        vector_search.search.return_value = [
            _make_vector_result(request_id=i, similarity=0.9 - i * 0.01) for i in range(5)
        ]
        payload = {"summary_250": "Test content"}
        result = await svc.find_related(payload)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_uses_title_from_metadata(
        self, service: RelatedReadsService, vector_search: MagicMock
    ) -> None:
        vector_search.search.return_value = [
            _make_vector_result(request_id=1, similarity=0.9),
        ]
        payload = {
            "summary_250": "Content",
            "metadata": {"title": "Metadata Title"},
        }
        result = await service.find_related(payload)
        assert len(result) == 1
        # The service should have called search with text containing the title
        vector_search.search.assert_called_once()
