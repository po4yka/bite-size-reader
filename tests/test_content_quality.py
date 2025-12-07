from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.external.firecrawl_parser import FirecrawlResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.config import AppConfig


@asynccontextmanager
async def _dummy_sem() -> AsyncIterator[None]:
    yield


def _make_extractor(
    db: MagicMock, response_formatter: MagicMock, firecrawl: MagicMock
) -> ContentExtractor:
    cfg = cast(
        "AppConfig",
        SimpleNamespace(
            runtime=SimpleNamespace(enable_textacy=False, request_timeout_sec=5),
            redis=SimpleNamespace(
                enabled=False,
                cache_enabled=False,
                prefix="test",
                required=False,
                cache_timeout_sec=0.1,
                firecrawl_ttl_seconds=0,
            ),
        ),
    )
    return ContentExtractor(
        cfg=cfg,
        db=db,
        firecrawl=firecrawl,
        response_formatter=response_formatter,
        audit_func=lambda *args, **kwargs: None,
        sem=_dummy_sem,
    )


def _firecrawl_result(markdown: str | None, html: str | None) -> FirecrawlResult:
    return FirecrawlResult(
        status="ok",
        http_status=200,
        content_markdown=markdown,
        content_html=html,
        structured_json=None,
        metadata_json=None,
        links_json=None,
        response_success=True,
        response_error_code=None,
        response_error_message=None,
        response_details=None,
        latency_ms=123,
        error_text=None,
        source_url="https://example.com",
        endpoint="/v2/scrape",
        options_json={"formats": ["markdown", "html"]},
        correlation_id="cid-123",
    )


@pytest.mark.asyncio
async def test_low_value_content_triggers_failure() -> None:
    db = MagicMock()
    db.async_update_request_status = AsyncMock()
    response_formatter = MagicMock()
    response_formatter.send_firecrawl_start_notification = AsyncMock()
    response_formatter.send_error_notification = AsyncMock()
    response_formatter.send_html_fallback_notification = AsyncMock()
    response_formatter.send_firecrawl_success_notification = AsyncMock()

    firecrawl = MagicMock()
    firecrawl.scrape_markdown = AsyncMock(
        return_value=_firecrawl_result(markdown="Close Close", html="<p>Close</p>")
    )

    extractor = _make_extractor(db, response_formatter, firecrawl)
    cast("Any", extractor)._attempt_direct_html_salvage = AsyncMock(return_value=None)

    with pytest.raises(ValueError) as exc_info:
        await extractor._perform_new_crawl(
            message=SimpleNamespace(),
            req_id=42,
            url_text="https://example.com",
            dedupe_hash="hash",
            correlation_id="cid-123",
            interaction_id=None,
            silent=False,
        )

    assert "insufficient_useful_content" in str(exc_info.value)
    db.async_update_request_status.assert_awaited_once_with(42, "error")
    response_formatter.send_error_notification.assert_awaited()
    response_formatter.send_firecrawl_success_notification.assert_not_awaited()

    assert db.insert_crawl_result.called
    inserted_kwargs = db.insert_crawl_result.call_args.kwargs
    assert inserted_kwargs["status"] == "error"
    assert "insufficient_useful_content" in inserted_kwargs["error_text"]


def test_detect_low_value_content_allows_substantive_text() -> None:
    db = MagicMock()
    response_formatter = MagicMock()
    firecrawl = MagicMock()

    extractor = _make_extractor(db, response_formatter, firecrawl)

    result = _firecrawl_result(
        markdown="# Heading\n\nThis short article explains the basics of Obsidian vault design.",
        html=None,
    )

    assert extractor._detect_low_value_content(result) is None
