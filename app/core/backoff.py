"""Shared exponential backoff with jitter.

Centralizes the backoff/sleep logic used by multiple adapters
(OpenRouter, Firecrawl, LLM clients) so the algorithm lives in one place.
"""

from __future__ import annotations

import asyncio
import random


async def sleep_backoff(attempt: int, backoff_base: float = 0.5) -> None:
    """Sleep with exponential backoff and jitter.

    Delay formula: ``max(0, backoff_base * 2^attempt) * (1 + uniform(-0.25, 0.25))``

    Args:
        attempt: Current attempt number (0-indexed).
        backoff_base: Base delay in seconds. Defaults to 0.5.
    """
    base_delay = max(0.0, backoff_base * (2**attempt))
    jitter = 1.0 + random.uniform(-0.25, 0.25)
    await asyncio.sleep(base_delay * jitter)
