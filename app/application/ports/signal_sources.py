"""Ports for proactive signal-source persistence."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SignalSourceRepositoryPort(Protocol):
    """Persistence port for Phase 3 signal-source entities."""

    async def async_upsert_source(
        self,
        *,
        kind: str,
        external_id: str | None = None,
        url: str | None = None,
        title: str | None = None,
        description: str | None = None,
        site_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update a generic source."""

    async def async_subscribe(
        self,
        *,
        user_id: int,
        source_id: int,
        topic_constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or reactivate a user's source subscription."""

    async def async_get_source(self, source_id: int) -> dict[str, Any] | None:
        """Return a source by ID."""

    async def async_set_source_active(self, source_id: int, *, is_active: bool) -> bool:
        """Enable or disable a source."""

    async def async_upsert_feed_item(
        self,
        *,
        source_id: int,
        external_id: str,
        canonical_url: str | None = None,
        title: str | None = None,
        content_text: str | None = None,
        author: str | None = None,
        published_at: Any | None = None,
        engagement: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update an ingested item."""

    async def async_list_user_subscriptions(self, user_id: int) -> list[dict[str, Any]]:
        """List subscriptions visible to a user."""

    async def async_list_user_signals(self, user_id: int) -> list[dict[str, Any]]:
        """List scored signal candidates visible to a user."""

    async def async_list_unscored_candidates(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """List active subscription/feed-item pairs that do not have a signal yet."""
