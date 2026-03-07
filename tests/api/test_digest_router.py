from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.models.digest import SubscribeRequest, TriggerDigestResponse
from app.api.routers import digest as digest_router


@pytest.mark.asyncio
async def test_trigger_digest_enqueues_background_job():
    digest_facade = AsyncMock()
    digest_facade.trigger_digest = AsyncMock(
        return_value=TriggerDigestResponse(
            status="queued",
            correlation_id="cid-digest-1",
        )
    )

    request = SimpleNamespace(state=SimpleNamespace(correlation_id="api-cid-1"))

    response = await digest_router.trigger_digest(
        current_user={"user_id": 123456789},
        request=request,
        digest_facade=digest_facade,
    )

    digest_facade.trigger_digest.assert_awaited_once_with(123456789)
    assert response["data"]["status"] == "queued"
    assert response["data"]["correlation_id"] == "cid-digest-1"


@pytest.mark.asyncio
async def test_trigger_channel_digest_enqueues_background_job():
    digest_facade = AsyncMock()
    digest_facade.trigger_channel_digest = AsyncMock(
        return_value={
            "status": "queued",
            "channel": "channel_name",
            "correlation_id": "cid-channel-1",
        }
    )

    request = SimpleNamespace(state=SimpleNamespace(correlation_id="api-cid-2"))

    with patch(
        "app.api.routers.digest.AuthService.require_owner", new=AsyncMock()
    ) as require_owner:
        response = await digest_router.trigger_channel_digest(
            body=SubscribeRequest(channel_username="@channel_name"),
            current_user={"user_id": 123456789},
            request=request,
            digest_facade=digest_facade,
        )

    require_owner.assert_awaited_once_with({"user_id": 123456789})
    digest_facade.trigger_channel_digest.assert_awaited_once_with(123456789, "@channel_name")
    assert response["data"]["status"] == "queued"
    assert response["data"]["channel"] == "channel_name"
    assert response["data"]["correlation_id"] == "cid-channel-1"
