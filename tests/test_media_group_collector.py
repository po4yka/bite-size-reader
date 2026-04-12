from __future__ import annotations

import asyncio

import pytest

from app.adapters.attachment.media_group_collector import MediaGroupCollector


@pytest.mark.asyncio
async def test_media_group_collector_returns_group_once_after_quiet_period() -> None:
    collector: MediaGroupCollector[int] = MediaGroupCollector(settle_delay_sec=0.01)

    first_task = asyncio.create_task(collector.collect(("chat", "album"), 1))
    await asyncio.sleep(0)
    second_task = asyncio.create_task(collector.collect(("chat", "album"), 2))

    first_result = await first_task
    second_result = await second_task

    assert first_result == [1, 2]
    assert second_result is None
