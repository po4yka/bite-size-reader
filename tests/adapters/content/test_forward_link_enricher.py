"""Tests for ForwardLinkEnricher -- folding embedded-link content into a forward prompt."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.content.forward_link_enricher import ForwardLinkEnricher


def _cfg(
    *,
    max_links: int = 5,
    per_article_chars: int = 8000,
    per_url_timeout_sec: float = 25.0,
) -> Any:
    return SimpleNamespace(
        runtime=SimpleNamespace(
            forward_link_max_links=max_links,
            forward_link_per_article_chars=per_article_chars,
            forward_link_per_url_timeout_sec=per_url_timeout_sec,
        )
    )


def _message(entities: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(entities=entities)


def _text_link(url: str) -> SimpleNamespace:
    return SimpleNamespace(type="text_link", url=url, offset=0, length=0)


def _extractor(side_effect: Any = None, return_value: Any = None) -> Any:
    mock = AsyncMock()
    if side_effect is not None:
        mock.extract_content_pure.side_effect = side_effect
    else:
        mock.extract_content_pure.return_value = return_value
    return mock


@pytest.mark.asyncio
async def test_no_links_returns_base_prompt_unchanged() -> None:
    extractor = _extractor()
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)

    result = await enricher.enrich(
        message=_message([]),
        base_prompt="Channel: X\n\npost text",
        post_text="post text",
        correlation_id="c1",
    )

    assert result == "Channel: X\n\npost text"
    extractor.extract_content_pure.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_folds_in_referenced_articles() -> None:
    async def _extract(url: str, cid: Any, request_id: Any = None) -> tuple[str, str, dict]:
        return (f"full body of {url}", "markdown", {"title": f"Title {url[-1]}"})

    extractor = _extractor(side_effect=_extract)
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)
    msg = _message([_text_link("https://a.com/1"), _text_link("https://b.com/2")])

    result = await enricher.enrich(
        message=msg,
        base_prompt="Channel: X\n\npost text",
        post_text="post text",
        correlation_id="c1",
    )

    assert result.startswith("Channel: X\n\npost text")
    assert "## Referenced article: Title 1" in result
    assert "## Referenced article: Title 2" in result
    assert "full body of https://a.com/1" in result
    assert "https://a.com/1" in result
    assert extractor.extract_content_pure.await_count == 2
    # sub-link scrapes must not carry a request_id (would mark the forward failed)
    for call in extractor.extract_content_pure.await_args_list:
        assert call.kwargs.get("request_id") is None


@pytest.mark.asyncio
async def test_max_links_cap_is_respected() -> None:
    async def _extract(url: str, cid: Any, request_id: Any = None) -> tuple[str, str, dict]:
        return (f"body {url}", "markdown", {})

    extractor = _extractor(side_effect=_extract)
    enricher = ForwardLinkEnricher(cfg=_cfg(max_links=2), content_extractor=extractor)
    msg = _message([_text_link(f"https://x.com/{i}") for i in range(4)])

    await enricher.enrich(
        message=msg,
        base_prompt="post",
        post_text="post",
        correlation_id="c1",
    )

    assert extractor.extract_content_pure.await_count == 2


@pytest.mark.asyncio
async def test_failed_scrape_is_skipped_others_survive() -> None:
    async def _extract(url: str, cid: Any, request_id: Any = None) -> tuple[str, str, dict]:
        if "bad" in url:
            raise ValueError("Low-value content detected")
        return ("good body", "markdown", {})

    extractor = _extractor(side_effect=_extract)
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)
    msg = _message([_text_link("https://bad.com/x"), _text_link("https://good.com/y")])

    result = await enricher.enrich(
        message=msg,
        base_prompt="post",
        post_text="post",
        correlation_id="c1",
    )

    assert "good body" in result
    assert "bad.com" not in result


@pytest.mark.asyncio
async def test_timeout_on_one_url_does_not_sink_enrichment() -> None:
    async def _extract(url: str, cid: Any, request_id: Any = None) -> tuple[str, str, dict]:
        if "slow" in url:
            await asyncio.sleep(1.0)
        return ("fast body", "markdown", {})

    extractor = _extractor(side_effect=_extract)
    enricher = ForwardLinkEnricher(cfg=_cfg(per_url_timeout_sec=0.05), content_extractor=extractor)
    msg = _message([_text_link("https://slow.com/x"), _text_link("https://fast.com/y")])

    result = await enricher.enrich(
        message=msg,
        base_prompt="post",
        post_text="post",
        correlation_id="c1",
    )

    assert "fast body" in result
    assert "slow.com" not in result


@pytest.mark.asyncio
async def test_all_scrapes_fail_returns_base_prompt() -> None:
    extractor = _extractor(side_effect=ValueError("Extraction failed"))
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)
    msg = _message([_text_link("https://a.com/1")])

    result = await enricher.enrich(
        message=msg,
        base_prompt="post body",
        post_text="post body",
        correlation_id="c1",
    )

    assert result == "post body"


@pytest.mark.asyncio
async def test_per_article_char_cap_truncates_body() -> None:
    async def _extract(url: str, cid: Any, request_id: Any = None) -> tuple[str, str, dict]:
        return ("z" * 50_000, "markdown", {"title": "Long"})

    extractor = _extractor(side_effect=_extract)
    enricher = ForwardLinkEnricher(cfg=_cfg(per_article_chars=2000), content_extractor=extractor)
    msg = _message([_text_link("https://a.com/1")])

    result = await enricher.enrich(
        message=msg,
        base_prompt="post",
        post_text="post",
        correlation_id="c1",
    )

    # the single section is bounded by the per-article cap, not 50k
    assert len(result) < 3000
    assert result.rstrip().endswith("[…]")


@pytest.mark.asyncio
async def test_oversized_base_prompt_skips_enrichment_before_fetching() -> None:
    extractor = _extractor()
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)
    huge = "x" * 44_000
    msg = _message([_text_link("https://a.com/1")])

    result = await enricher.enrich(
        message=msg,
        base_prompt=huge,
        post_text="post",
        correlation_id="c1",
    )

    assert result == huge
    extractor.extract_content_pure.assert_not_awaited()


@pytest.mark.asyncio
async def test_unexpected_error_falls_back_to_base_prompt() -> None:
    extractor = AsyncMock()
    enricher = ForwardLinkEnricher(cfg=_cfg(), content_extractor=extractor)

    # an unexpected failure deep in _enrich must never propagate out of the
    # forward flow -- the post is still summarized from its own text.
    with patch(
        "app.adapters.content.forward_link_enricher.extract_forward_urls",
        side_effect=RuntimeError("boom"),
    ):
        result = await enricher.enrich(
            message=_message([]),
            base_prompt="post body",
            post_text="post body",
            correlation_id="c1",
        )

    assert result == "post body"
