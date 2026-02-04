"""Bot shutdown must close external clients and drain tasks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_bot():
    from app.adapters.telegram.telegram_bot import TelegramBot

    bot = TelegramBot.__new__(TelegramBot)
    bot.cfg = MagicMock()
    bot._firecrawl = MagicMock()
    bot._firecrawl.aclose = AsyncMock()
    bot._llm_client = MagicMock()
    bot._llm_client.aclose = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_shutdown_closes_firecrawl_client():
    bot = _make_bot()
    await bot._shutdown()
    bot._firecrawl.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_closes_llm_client():
    bot = _make_bot()
    await bot._shutdown()
    bot._llm_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_cleans_openrouter_pool():
    bot = _make_bot()
    with patch(
        "app.adapters.openrouter.openrouter_client.OpenRouterClient.cleanup_all_clients",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        await bot._shutdown()
        mock_cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_tolerates_client_close_failure():
    """Shutdown must not crash if a client's aclose() raises."""
    bot = _make_bot()
    bot._firecrawl.aclose = AsyncMock(side_effect=RuntimeError("close failed"))
    # Should not raise
    await bot._shutdown()
    # LLM client should still be closed even if firecrawl fails
    bot._llm_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_closes_vector_store():
    bot = _make_bot()
    bot.vector_store = MagicMock()
    bot.vector_store.aclose = AsyncMock()
    await bot._shutdown()
    bot.vector_store.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_closes_embedding_service():
    bot = _make_bot()
    bot.embedding_service = MagicMock()
    bot.embedding_service.aclose = AsyncMock()
    await bot._shutdown()
    bot.embedding_service.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_drains_audit_tasks():
    """Shutdown should await in-flight audit tasks."""
    completed = False

    async def slow_audit():
        nonlocal completed
        await asyncio.sleep(0.01)
        completed = True

    bot = _make_bot()
    bot._audit_tasks = {asyncio.create_task(slow_audit())}
    await bot._shutdown(drain_timeout=2.0)
    assert completed
