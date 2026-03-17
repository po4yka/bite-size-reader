from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.services.digest_facade import DigestFacade, get_digest_facade
from app.config.digest import ChannelDigestConfig


@pytest.mark.asyncio
async def test_digest_facade_delegates_sync_methods() -> None:
    service = MagicMock()
    service.list_subscriptions.return_value = {"channels": []}
    service.subscribe_channel.return_value = {"status": "created", "username": "chan"}
    service.unsubscribe_channel.return_value = {"status": "unsubscribed", "username": "chan"}
    service.list_channel_posts.return_value = {"posts": [], "total": 0}
    service.get_preferences.return_value = {"timezone": "UTC"}
    service.update_preferences.return_value = {"delivery_time": "12:00"}
    service.list_deliveries.return_value = {"deliveries": [], "total": 0}
    service.list_categories.return_value = [{"id": 1, "name": "News"}]
    service.create_category.return_value = {"id": 1, "name": "News"}
    service.update_category.return_value = {"id": 1, "name": "Updated"}
    service.delete_category.return_value = {"status": "deleted"}
    service.assign_category.return_value = {"status": "updated"}
    service.bulk_unsubscribe.return_value = {"results": [], "success_count": 1, "error_count": 0}
    service.bulk_assign_category.return_value = {
        "results": [],
        "success_count": 2,
        "error_count": 0,
    }

    facade = DigestFacade(
        config_factory=ChannelDigestConfig,
        service_factory=lambda cfg: service,
    )

    assert await facade.list_channels(10) == {"channels": []}
    assert await facade.subscribe_channel(10, "@chan") == {"status": "created", "username": "chan"}
    assert await facade.unsubscribe_channel(10, "@chan") == {
        "status": "unsubscribed",
        "username": "chan",
    }
    assert await facade.list_channel_posts(10, "@chan", limit=5, offset=2) == {
        "posts": [],
        "total": 0,
    }
    assert await facade.get_preferences(10) == {"timezone": "UTC"}
    assert await facade.update_preferences(10, delivery_time="12:00") == {"delivery_time": "12:00"}
    assert await facade.list_history(10, limit=20, offset=1) == {"deliveries": [], "total": 0}
    assert await facade.list_categories(10) == [{"id": 1, "name": "News"}]
    assert await facade.create_category(10, "News") == {"id": 1, "name": "News"}
    assert await facade.update_category(10, 1, name="Updated") == {"id": 1, "name": "Updated"}
    assert await facade.delete_category(10, 1) == {"status": "deleted"}
    assert await facade.assign_category(10, 22, 1) == {"status": "updated"}
    assert await facade.bulk_unsubscribe(10, ["a", "b"]) == {
        "results": [],
        "success_count": 1,
        "error_count": 0,
    }
    assert await facade.bulk_assign_category(10, [1, 2], 1) == {
        "results": [],
        "success_count": 2,
        "error_count": 0,
    }

    service.list_subscriptions.assert_called_once_with(10)
    service.subscribe_channel.assert_called_once_with(10, "@chan")
    service.unsubscribe_channel.assert_called_once_with(10, "@chan")
    service.list_channel_posts.assert_called_once_with(10, "@chan", limit=5, offset=2)
    service.get_preferences.assert_called_once_with(10)
    service.update_preferences.assert_called_once_with(10, delivery_time="12:00")
    service.list_deliveries.assert_called_once_with(10, limit=20, offset=1)
    service.list_categories.assert_called_once_with(10)
    service.create_category.assert_called_once_with(10, "News")
    service.update_category.assert_called_once_with(10, 1, name="Updated")
    service.delete_category.assert_called_once_with(10, 1)
    service.assign_category.assert_called_once_with(10, 22, 1)
    service.bulk_unsubscribe.assert_called_once_with(10, ["a", "b"])
    service.bulk_assign_category.assert_called_once_with(10, [1, 2], 1)


@pytest.mark.asyncio
async def test_digest_facade_resolve_channel_delegates_async_call() -> None:
    service = MagicMock()
    service.resolve_channel = AsyncMock(
        return_value=SimpleNamespace(username="resolved", title="Resolved")
    )

    facade = DigestFacade(
        config_factory=ChannelDigestConfig,
        service_factory=lambda cfg: service,
    )

    result = await facade.resolve_channel(55, "@resolved")

    assert result.username == "resolved"
    service.resolve_channel.assert_awaited_once_with(55, "@resolved")


@pytest.mark.asyncio
async def test_digest_facade_trigger_digest_enqueues_job() -> None:
    service = MagicMock()
    service.trigger_digest.return_value = SimpleNamespace(status="queued", correlation_id="cid-123")
    service.enqueue_digest_trigger = AsyncMock()

    facade = DigestFacade(
        config_factory=ChannelDigestConfig,
        service_factory=lambda cfg: service,
    )

    result = await facade.trigger_digest(77)

    assert result.correlation_id == "cid-123"
    service.enqueue_digest_trigger.assert_awaited_once_with(user_id=77, correlation_id="cid-123")


@pytest.mark.asyncio
async def test_digest_facade_trigger_channel_digest_uses_normalized_channel() -> None:
    service = MagicMock()
    service.trigger_channel_digest.return_value = {
        "status": "queued",
        "channel": "examplechannel",
        "correlation_id": "cid-456",
    }
    service.enqueue_channel_digest_trigger = AsyncMock()

    facade = DigestFacade(
        config_factory=ChannelDigestConfig,
        service_factory=lambda cfg: service,
    )

    result = await facade.trigger_channel_digest(88, "@ExampleChannel")

    assert result["channel"] == "examplechannel"
    service.enqueue_channel_digest_trigger.assert_awaited_once_with(
        user_id=88,
        channel_username="examplechannel",
        correlation_id="cid-456",
    )


def test_get_digest_facade_returns_default_instance() -> None:
    assert isinstance(get_digest_facade(), DigestFacade)
