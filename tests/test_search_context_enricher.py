import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.adapters.content.search_context_enricher import SearchContextEnricher


@pytest.mark.asyncio
async def test_disabled_search_returns_empty_context() -> None:
    cfg = SimpleNamespace(web_search=SimpleNamespace(enabled=False))
    enricher = SearchContextEnricher(
        cfg=cfg,
        openrouter=SimpleNamespace(),
        topic_search=None,
    )

    result = await enricher.enrich(
        content_text="content",
        chosen_lang="en",
        correlation_id="cid-disabled",
    )

    assert result == ""


@pytest.mark.asyncio
async def test_runtime_errors_return_empty_context() -> None:
    cfg = SimpleNamespace(
        web_search=SimpleNamespace(
            enabled=True,
            min_content_length=1,
        )
    )
    enricher = SearchContextEnricher(
        cfg=cfg,
        openrouter=SimpleNamespace(),
        topic_search=cast("Any", SimpleNamespace()),
    )

    with patch("app.agents.web_search_agent.WebSearchAgent") as agent_cls:
        agent_cls.return_value.execute = AsyncMock(side_effect=RuntimeError("search failed"))
        result = await enricher.enrich(
            content_text="content",
            chosen_lang="en",
            correlation_id="cid-error",
        )

    assert result == ""


@pytest.mark.asyncio
async def test_cancelled_error_propagates() -> None:
    cfg = SimpleNamespace(
        web_search=SimpleNamespace(
            enabled=True,
            min_content_length=1,
        )
    )
    enricher = SearchContextEnricher(
        cfg=cfg,
        openrouter=SimpleNamespace(),
        topic_search=cast("Any", SimpleNamespace()),
    )

    with patch("app.agents.web_search_agent.WebSearchAgent") as agent_cls:
        agent_cls.return_value.execute = AsyncMock(side_effect=asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await enricher.enrich(
                content_text="content",
                chosen_lang="en",
                correlation_id="cid-cancel",
            )
