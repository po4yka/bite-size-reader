"""User, audit, batch-session, sync, and backup ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@runtime_checkable
class UserRepositoryPort(Protocol):
    async def async_insert_user_interaction(
        self,
        *,
        user_id: int,
        interaction_type: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        command: str | None = None,
        input_text: str | None = None,
        input_url: str | None = None,
        has_forward: bool = False,
        forward_from_chat_id: int | None = None,
        forward_from_chat_title: str | None = None,
        forward_from_message_id: int | None = None,
        media_type: str | None = None,
        correlation_id: str | None = None,
        structured_output_enabled: bool = False,
    ) -> int:
        """Persist a user interaction."""

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> None:
        """Update a persisted user interaction."""

    async def async_upsert_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None = None,
        is_owner: bool = False,
    ) -> None:
        """Upsert a user row."""

    async def async_upsert_chat(
        self,
        *,
        chat_id: int,
        type_: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
        """Upsert a chat row."""

    async def async_get_user_by_telegram_id(self, telegram_user_id: int) -> dict[str, Any] | None:
        """Return user by Telegram identifier."""

    async def async_get_or_create_user(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        is_owner: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Return an existing user or create one."""

    async def async_set_link_nonce(
        self,
        *,
        telegram_user_id: int,
        nonce: str,
        expires_at: datetime,
    ) -> None:
        """Store a Telegram linking nonce."""

    async def async_clear_link_nonce(self, *, telegram_user_id: int) -> None:
        """Clear a Telegram linking nonce."""

    async def async_complete_telegram_link(
        self,
        *,
        telegram_user_id: int,
        linked_telegram_user_id: int,
        username: str | None,
        photo_url: str | None,
        first_name: str | None,
        last_name: str | None,
        linked_at: datetime,
    ) -> None:
        """Persist completed Telegram link metadata."""

    async def async_unlink_telegram(self, *, telegram_user_id: int) -> None:
        """Remove Telegram link metadata."""

    async def async_delete_user(self, *, telegram_user_id: int) -> None:
        """Delete a user and related data."""

    async def async_update_user_preferences(
        self,
        telegram_user_id: int,
        preferences: dict[str, Any],
    ) -> None:
        """Update user preferences."""

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version for the user identified by *user_id* (telegram_user_id)."""


@runtime_checkable
class AuditLogRepositoryPort(Protocol):
    async def async_insert_audit_log(
        self,
        log_level: str,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        """Persist an audit log row."""


@runtime_checkable
class BatchSessionRepositoryPort(Protocol):
    async def async_create_batch_session(
        self,
        user_id: int,
        correlation_id: str,
        total_urls: int,
    ) -> int:
        """Create a batch session."""

    async def async_add_batch_session_item(
        self,
        session_id: int,
        request_id: int,
        position: int,
        is_series_part: bool = False,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> int:
        """Persist a batch session item."""

    async def async_get_batch_session_items(self, session_id: int) -> list[dict[str, Any]]:
        """Return batch session items."""

    async def async_update_batch_session_status(
        self,
        session_id: int,
        status: str,
        analysis_status: str | None = None,
        processing_time_ms: int | None = None,
    ) -> None:
        """Update batch session status."""

    async def async_update_batch_session_counts(
        self,
        session_id: int,
        successful_count: int,
        failed_count: int,
    ) -> None:
        """Update batch session counters."""

    async def async_update_batch_session_relationship(
        self,
        session_id: int,
        relationship_type: str,
        relationship_confidence: float,
        relationship_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update batch relationship state."""

    async def async_update_batch_session_combined_summary(
        self,
        session_id: int,
        combined_summary: dict[str, Any],
    ) -> None:
        """Persist combined batch summary state."""

    async def async_update_batch_session_item_series_info(
        self,
        item_id: int,
        is_series_part: bool,
        series_order: int | None = None,
        series_title: str | None = None,
    ) -> None:
        """Persist per-item series metadata."""


@runtime_checkable
class KarakeepSyncRepositoryPort(Protocol):
    async def async_get_synced_hashes_by_direction(self, sync_direction: str) -> set[str]:
        """Return hashes already synced in the given direction."""

    async def async_create_sync_record(
        self,
        *,
        bsr_summary_id: int | None = None,
        karakeep_bookmark_id: str | None = None,
        url_hash: str,
        sync_direction: str,
        synced_at: datetime | None = None,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> int | None:
        """Create a sync record."""

    async def async_get_summaries_for_sync(
        self, user_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Return summaries prepared for Karakeep sync."""

    async def async_get_existing_request_hashes(self) -> set[str]:
        """Return hashes for existing request rows."""

    async def async_create_request_from_karakeep(
        self,
        *,
        user_id: int,
        input_url: str,
        normalized_url: str | None,
        dedupe_hash: str | None,
    ) -> int:
        """Create a request row from Karakeep data."""

    async def async_get_sync_stats(self) -> dict[str, Any]:
        """Return aggregate sync statistics."""

    async def async_get_crawl_result_title(self, request_id: int) -> str | None:
        """Return crawl-result title for a request."""

    async def async_get_synced_items_with_bookmark_and_summary(self) -> list[dict[str, Any]]:
        """Return synced bookmark/summary rows."""

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary by ID."""

    async def async_update_summary_status(
        self,
        summary_id: int,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
    ) -> None:
        """Update summary sync status fields."""

    async def async_update_sync_timestamps(
        self,
        sync_id: int,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> None:
        """Update persisted sync timestamps."""

    async def async_delete_all_sync_records(self, direction: str | None = None) -> int:
        """Delete sync rows."""

    async def async_upsert_sync_record(
        self,
        *,
        bsr_summary_id: int | None = None,
        karakeep_bookmark_id: str | None = None,
        url_hash: str,
        sync_direction: str,
        synced_at: datetime | None = None,
        bsr_modified_at: datetime | None = None,
        karakeep_modified_at: datetime | None = None,
    ) -> int:
        """Create or update a sync record."""


@runtime_checkable
class BackupRepositoryPort(Protocol):
    """Port for user backup archive operations."""

    async def async_create_backup(
        self, user_id: int, backup_type: str = "manual"
    ) -> dict[str, Any]:
        """Insert a new UserBackup and return the created record."""

    async def async_get_backup(self, backup_id: int) -> dict[str, Any] | None:
        """Return a single backup by ID."""

    async def async_list_backups(self, user_id: int) -> list[dict[str, Any]]:
        """List user's backups, ordered by created_at DESC."""

    async def async_update_backup(self, backup_id: int, **fields: Any) -> None:
        """Update provided fields on a backup record."""

    async def async_delete_backup(self, backup_id: int) -> None:
        """Hard delete a backup record."""

    async def async_count_recent_backups(self, user_id: int, since_hours: int = 1) -> int:
        """Count backups created within the last N hours (for rate limiting)."""
