"""Facade for digest API orchestration used by HTTP routers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.services.digest_api_service import DigestAPIService
from app.config.digest import ChannelDigestConfig

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.api.models.digest import (
        CategoryResponse,
        DigestPreferenceResponse,
        ResolveChannelResponse,
        TriggerDigestResponse,
    )


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

    # --- Channels ---

    async def list_channels(self, user_id: int) -> dict[str, Any]:
        return self._service().list_subscriptions(user_id)

    async def subscribe_channel(self, user_id: int, channel_username: str) -> dict[str, str]:
        return self._service().subscribe_channel(user_id, channel_username)

    async def unsubscribe_channel(self, user_id: int, channel_username: str) -> dict[str, str]:
        return self._service().unsubscribe_channel(user_id, channel_username)

    async def resolve_channel(self, user_id: int, username: str) -> ResolveChannelResponse:
        return await self._service().resolve_channel(user_id, username)

    # --- Posts ---

    async def list_channel_posts(
        self, user_id: int, username: str, *, limit: int, offset: int
    ) -> dict[str, Any]:
        return self._service().list_channel_posts(user_id, username, limit=limit, offset=offset)

    # --- Preferences ---

    async def get_preferences(self, user_id: int) -> DigestPreferenceResponse:
        return self._service().get_preferences(user_id)

    async def update_preferences(self, user_id: int, **fields: Any) -> DigestPreferenceResponse:
        return self._service().update_preferences(user_id, **fields)

    # --- History ---

    async def list_history(self, user_id: int, *, limit: int, offset: int) -> dict[str, Any]:
        return self._service().list_deliveries(user_id, limit=limit, offset=offset)

    # --- Triggers ---

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

    # --- Categories ---

    async def list_categories(self, user_id: int) -> list[CategoryResponse]:
        return self._service().list_categories(user_id)

    async def create_category(self, user_id: int, name: str) -> CategoryResponse:
        return self._service().create_category(user_id, name)

    async def update_category(
        self, user_id: int, category_id: int, **fields: Any
    ) -> CategoryResponse:
        return self._service().update_category(user_id, category_id, **fields)

    async def delete_category(self, user_id: int, category_id: int) -> dict[str, str]:
        return self._service().delete_category(user_id, category_id)

    async def assign_category(
        self, user_id: int, subscription_id: int, category_id: int | None
    ) -> dict[str, str]:
        return self._service().assign_category(user_id, subscription_id, category_id)

    # --- Bulk operations ---

    async def bulk_unsubscribe(self, user_id: int, usernames: list[str]) -> dict[str, Any]:
        return self._service().bulk_unsubscribe(user_id, usernames)

    async def bulk_assign_category(
        self, user_id: int, subscription_ids: list[int], category_id: int | None
    ) -> dict[str, Any]:
        return self._service().bulk_assign_category(user_id, subscription_ids, category_id)


def get_digest_facade() -> DigestFacade:
    """FastAPI dependency provider for DigestFacade."""
    return DigestFacade()
