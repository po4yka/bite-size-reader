"""Tests for platform extraction router GitHub registration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.platform_extraction import (
    PlatformExtractionRequest,
    PlatformExtractionRouter,
)


def _make_router_with_mocks() -> tuple[PlatformExtractionRouter, MagicMock, MagicMock]:
    """Return a router with a mock GitHub extractor registered before a mock fallback."""
    from app.adapters.content.platform_extraction.models import PlatformExtractionResult

    github_result = PlatformExtractionResult(
        platform="github",
        request_id=None,
        content_text="repo content",
        content_source="github_api",
        detected_lang="en",
        title="owner/repo",
        metadata={},
    )
    github_extractor = MagicMock()
    github_extractor.supports.return_value = True
    github_extractor.extract = AsyncMock(return_value=github_result)

    fallback_extractor = MagicMock()
    fallback_extractor.supports.return_value = True
    fallback_extractor.extract = AsyncMock(return_value=None)

    from app.adapters.github.url_patterns import is_github_repo_url

    router = PlatformExtractionRouter()
    router.register(predicate=is_github_repo_url, factory=lambda: github_extractor)
    router.register(predicate=lambda _: True, factory=lambda: fallback_extractor)

    return router, github_extractor, fallback_extractor


def _make_request(url: str) -> PlatformExtractionRequest:
    return PlatformExtractionRequest(
        message=None,
        url_text=url,
        normalized_url=url,
        correlation_id="test-cid",
        silent=True,
        mode="pure",
    )


class TestGitHubRouterRegistration:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_github_url_is_dispatched_to_github_extractor(self) -> None:
        router, github_extractor, fallback_extractor = _make_router_with_mocks()
        result = await router.extract(_make_request("https://github.com/owner/repo"))
        github_extractor.extract.assert_awaited_once()
        fallback_extractor.extract.assert_not_awaited()
        assert result is not None
        assert result.platform == "github"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_non_github_url_does_not_hit_github_extractor(self) -> None:
        router, github_extractor, fallback_extractor = _make_router_with_mocks()
        result = await router.extract(_make_request("https://example.com/article"))
        github_extractor.extract.assert_not_awaited()
        fallback_extractor.extract.assert_awaited_once()

    @pytest.mark.asyncio(loop_scope="function")
    async def test_github_extractor_registered_before_generic_scraper_chain(self) -> None:
        """GitHub entry must appear at index 0 so repo URLs short-circuit the generic chain."""
        from app.adapters.github.url_patterns import is_github_repo_url

        router = PlatformExtractionRouter()
        router.register(predicate=is_github_repo_url, factory=MagicMock())
        router.register(predicate=lambda _: True, factory=MagicMock())

        # Index 0 is github (predicate matches a known repo URL)
        assert router._entries[0][0]("https://github.com/owner/repo") is True
        # Index 1 is the generic fallback that matches everything
        assert router._entries[1][0]("https://github.com/owner/repo") is True
        assert router._entries[1][0]("https://example.com/article") is True
