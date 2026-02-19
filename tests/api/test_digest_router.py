from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.models.digest import TriggerDigestResponse
from app.api.routers import digest as digest_router


@pytest.mark.asyncio
async def test_trigger_digest_enqueues_background_job():
    service = MagicMock()
    service.trigger_digest.return_value = TriggerDigestResponse(
        status="queued",
        correlation_id="cid-digest-1",
    )
    service.enqueue_digest_trigger = AsyncMock()

    request = SimpleNamespace(state=SimpleNamespace(correlation_id="api-cid-1"))

    with patch.object(digest_router, "_get_service", return_value=service):
        response = await digest_router.trigger_digest(
            current_user={"user_id": 123456789},
            request=request,
        )

    service.trigger_digest.assert_called_once_with(123456789)
    service.enqueue_digest_trigger.assert_awaited_once_with(
        user_id=123456789,
        correlation_id="cid-digest-1",
    )
    assert response["data"]["status"] == "queued"
    assert response["data"]["correlation_id"] == "cid-digest-1"


@pytest.mark.asyncio
async def test_trigger_channel_digest_enqueues_background_job():
    service = MagicMock()
    service.trigger_channel_digest.return_value = {
        "status": "queued",
        "channel": "channel_name",
        "correlation_id": "cid-channel-1",
    }
    service.enqueue_channel_digest_trigger = AsyncMock()

    request = SimpleNamespace(state=SimpleNamespace(correlation_id="api-cid-2"))

    with patch.object(digest_router, "_get_service", return_value=service):
        response = await digest_router.trigger_channel_digest(
            request_body={"channel_username": "@channel_name"},
            current_user={"user_id": 123456789},
            request=request,
        )

    service.trigger_channel_digest.assert_called_once_with(123456789, "@channel_name")
    service.enqueue_channel_digest_trigger.assert_awaited_once_with(
        user_id=123456789,
        channel_username="channel_name",
        correlation_id="cid-channel-1",
    )
    assert response["data"]["status"] == "queued"
    assert response["data"]["channel"] == "channel_name"
    assert response["data"]["correlation_id"] == "cid-channel-1"
