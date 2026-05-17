from __future__ import annotations

from typing import Any

import pytest

from app.adapters.rss.rss_delivery_service import RSSDeliveryService
from app.config.rss import RSSConfig


class _FakeRSSRepository:
    def __init__(self, targets: list[dict[str, Any]]) -> None:
        self.targets = targets
        self.marked: list[tuple[int, int]] = []

    async def async_list_delivery_targets(
        self, new_item_ids: list[int] | None
    ) -> list[dict[str, Any]]:
        return self.targets

    async def async_mark_item_delivered(self, *, user_id: int, item_id: int) -> None:
        self.marked.append((user_id, item_id))


class _FakePureSummaryService:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def summarize(self, request: Any) -> dict[str, Any]:
        self.requests.append(request)
        return {
            "tldr": "Short version",
            "summary_250": "Summary body",
            "key_ideas": ["First", "Second"],
            "topic_tags": ["rss", "performance"],
        }


@pytest.mark.asyncio
async def test_rss_delivery_summarizes_once_per_item_for_multiple_subscribers() -> None:
    repo = _FakeRSSRepository(
        [
            {
                "id": 5,
                "title": "Shared item",
                "url": "https://example.com/shared",
                "content": "Long enough RSS content for one shared summary.",
                "subscriber_ids": [101, 102],
            }
        ]
    )
    pure = _FakePureSummaryService()
    service = RSSDeliveryService(
        cfg=RSSConfig(enabled=True, min_content_length=10),
        pure_summary_service=pure,  # type: ignore[arg-type]
        system_prompt_loader=lambda lang: f"prompt:{lang}",
        rss_repository=repo,  # type: ignore[arg-type]
    )
    sent: list[tuple[int, str]] = []

    async def send_func(user_id: int, text: str) -> None:
        sent.append((user_id, text))
        if user_id == 101:
            raise RuntimeError("send failed")

    stats = await service.deliver_new_items(send_func, new_item_ids=[5])

    assert stats == {"delivered": 1, "errors": 1, "skipped": 0}
    assert len(pure.requests) == 1
    assert [user_id for user_id, _ in sent] == [101, 102]
    assert sent[0][1] == sent[1][1]
    assert repo.marked == [(102, 5)]


@pytest.mark.asyncio
async def test_rss_delivery_marks_short_unscrapable_item_skipped_for_each_subscriber() -> None:
    repo = _FakeRSSRepository(
        [
            {
                "id": 6,
                "title": "Empty item",
                "url": None,
                "content": "",
                "subscriber_ids": [201, 202],
            }
        ]
    )
    pure = _FakePureSummaryService()
    service = RSSDeliveryService(
        cfg=RSSConfig(enabled=True, min_content_length=10),
        pure_summary_service=pure,  # type: ignore[arg-type]
        system_prompt_loader=lambda lang: f"prompt:{lang}",
        rss_repository=repo,  # type: ignore[arg-type]
    )
    sent: list[tuple[int, str]] = []

    async def send_func(user_id: int, text: str) -> None:
        sent.append((user_id, text))

    stats = await service.deliver_new_items(send_func, new_item_ids=[6])

    assert stats == {"delivered": 0, "errors": 0, "skipped": 2}
    assert pure.requests == []
    assert sent == []
    assert repo.marked == [(201, 6), (202, 6)]
