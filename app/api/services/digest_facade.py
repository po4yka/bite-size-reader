"""Facade for digest API orchestration used by HTTP routers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.services.digest_api_service import DigestAPIService
from app.config.digest import ChannelDigestConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.api.models.digest import DigestPreferenceResponse, TriggerDigestResponse


class DigestFacade:
    """Coordinates digest API service composition and async trigger workflows."""

    def __init__(
        self,
        config_factory: Callable[[], ChannelDigestConfig] | None = None,
        service_factory: Callable[[ChannelDigestConfig], DigestAPIService] | None = None,
    ) -> None:
        self._config_factory = config_factory or ChannelDigestConfig
        self._service_factory = service_factory or DigestAPIService

    def _service(self) -> DigestAPIService:
        return self._service_factory(self._config_factory())

    def list_channels(self, user_id: int) -> dict[str, Any]:
        return self._service().list_subscriptions(user_id)

    def subscribe_channel(self, user_id: int, channel_username: str) -> dict[str, str]:
        return self._service().subscribe_channel(user_id, channel_username)

    def unsubscribe_channel(self, user_id: int, channel_username: str) -> dict[str, str]:
        return self._service().unsubscribe_channel(user_id, channel_username)

    def get_preferences(self, user_id: int) -> DigestPreferenceResponse:
        return self._service().get_preferences(user_id)

    def update_preferences(self, user_id: int, **fields: Any) -> DigestPreferenceResponse:
        return self._service().update_preferences(user_id, **fields)

    def list_history(self, user_id: int, *, limit: int, offset: int) -> dict[str, Any]:
        return self._service().list_deliveries(user_id, limit=limit, offset=offset)

    async def trigger_digest(self, user_id: int) -> TriggerDigestResponse:
        service = self._service()
        data = service.trigger_digest(user_id)
        await service.enqueue_digest_trigger(
            user_id=user_id,
            correlation_id=data.correlation_id,
        )
        return data

    async def trigger_channel_digest(self, user_id: int, channel_username: str) -> dict[str, str]:
        service = self._service()
        data = service.trigger_channel_digest(user_id, channel_username)
        await service.enqueue_channel_digest_trigger(
            user_id=user_id,
            channel_username=data["channel"],
            correlation_id=data["correlation_id"],
        )
        return data


def get_digest_facade() -> DigestFacade:
    """FastAPI dependency provider for DigestFacade."""
    return DigestFacade()
