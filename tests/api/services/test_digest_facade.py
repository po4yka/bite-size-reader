from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.services.digest_facade import DigestFacade
from app.config.digest import ChannelDigestConfig


def test_digest_facade_delegates_sync_methods() -> None:
    service = MagicMock()
    service.list_subscriptions.return_value = {"channels": []}
    service.update_preferences.return_value = {"delivery_time": "12:00"}

    facade = DigestFacade(
        config_factory=ChannelDigestConfig,
        service_factory=lambda cfg: service,
    )

    assert facade.list_channels(10) == {"channels": []}
    assert facade.update_preferences(10, delivery_time="12:00") == {"delivery_time": "12:00"}
    service.list_subscriptions.assert_called_once_with(10)
    service.update_preferences.assert_called_once_with(10, delivery_time="12:00")


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
