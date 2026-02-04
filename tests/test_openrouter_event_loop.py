"""OpenRouter client pool must require a running event loop."""

from __future__ import annotations

import asyncio

import pytest

from app.adapters.openrouter.openrouter_client import OpenRouterClient


def test_get_event_loop_raises_outside_async():
    """_get_event_loop must raise RuntimeError when no loop is running."""
    with pytest.raises(RuntimeError):
        OpenRouterClient._get_event_loop()


@pytest.mark.asyncio
async def test_get_event_loop_returns_running_loop():
    """_get_event_loop must return the running loop inside async context."""
    loop = OpenRouterClient._get_event_loop()
    assert loop is asyncio.get_running_loop()
