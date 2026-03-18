"""Canonical application-layer ports.

Production code outside ``app/di`` should depend on these contracts rather than
concrete SQLite adapters or adapter-local compatibility protocols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypedDict, runtime_checkable

from app.domain.models.request import RequestStatus

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


class LLMCallRecord(TypedDict, total=False):
    """Typed record for persisting an LLM call."""

    request_id: int | None
    provider: str | None
    model: str | None
    endpoint: str | None
    request_headers_json: Any
    request_messages_json: Any
    response_text: str | None
    response_json: Any
    tokens_prompt: int | None
    tokens_completion: int | None
    cost_usd: float | None
    latency_ms: int | None
    status: str | None
    error_text: str | None
    structured_output_used: bool | None
    structured_output_mode: str | None
    error_context_json: Any


@runtime_checkable
class SummaryRepositoryPort(Protocol):
    """Port for summary query/update operations used in application use cases."""

    async def async_get_user_summaries(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        lang: str | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Return user summaries with pagination metadata."""

    async def async_get_user_summaries_for_insights(
        self,
        user_id: int,
        request_created_after: datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return summary rows used for insights/statistics."""

    async def async_get_unread_summaries(
        self,
        user_id: int | None,
        chat_id: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return unread summaries for user/chat."""

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary by ID."""

    async def async_get_summary_context_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary joined with its request and crawl result."""

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Return summary by request ID."""

    async def async_get_summary_id_by_request(self, request_id: int) -> int | None:
        """Return summary ID by request ID."""

    async def async_get_summaries_by_request_ids(
        self, request_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        """Return summaries mapped by request ID."""

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return all summaries for sync operations."""

    async def async_get_summary_for_sync_apply(
        self, summary_id: int, user_id: int
    ) -> dict[str, Any] | None:
        """Return a summary validated for sync-apply ownership."""

    async def async_apply_sync_change(
        self,
        summary_id: int,
        *,
        is_deleted: bool | None = None,
        deleted_at: datetime | None = None,
        is_read: bool | None = None,
    ) -> int:
        """Apply a sync mutation and return the new server version."""

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Mark summary as read."""

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Mark summary as unread."""

    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None:
        """Return unread summary by request ID."""

    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int:
        """Create or update a summary."""

    async def async_finalize_request_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
        request_status: RequestStatus = RequestStatus.COMPLETED,
    ) -> int:
        """Persist summary and update request status."""

    async def async_update_summary_insights(
        self,
        request_id: int,
        insights_json: dict[str, Any],
    ) -> None:
        """Persist summary insights JSON."""

    async def async_update_reading_progress(
        self,
        summary_id: int,
        progress: float,
        last_read_offset: int,
    ) -> None:
        """Update reading progress and last-read offset."""

    async def async_soft_delete_summary(self, summary_id: int) -> None:
        """Soft-delete summary."""

    async def async_toggle_favorite(self, summary_id: int) -> bool:
        """Toggle favorite status and return the new state."""

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version for summaries owned by *user_id*."""

    async def async_upsert_feedback(
        self,
        user_id: int,
        summary_id: int,
        rating: int | None,
        issues: list[str] | None,
        comment: str | None,
    ) -> dict[str, Any]:
        """Create or update feedback for a summary. Returns the feedback record dict."""


@runtime_checkable
class RequestRepositoryPort(Protocol):
    """Port for request read operations used in application use cases."""

    async def async_get_request_id_by_url_with_summary(self, user_id: int, url: str) -> int | None:
        """Return request ID for URL owned by user that has a summary."""

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Return request by ID."""

    async def async_get_request_context(self, request_id: int) -> dict[str, Any] | None:
        """Return request joined with its crawl result and summary."""

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Return request by dedupe hash."""

    async def async_get_requests_by_ids(
        self, request_ids: list[int], user_id: int | None = None
    ) -> dict[int, dict[str, Any]]:
        """Return requests mapped by ID."""

    async def async_create_request(
        self,
        *,
        type_: str = "url",
        status: RequestStatus = RequestStatus.PENDING,
        correlation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
        input_url: str | None = None,
        normalized_url: str | None = None,
        dedupe_hash: str | None = None,
        input_message_id: int | None = None,
        fwd_from_chat_id: int | None = None,
        fwd_from_msg_id: int | None = None,
        lang_detected: str | None = None,
        content_text: str | None = None,
        route_version: int = 1,
    ) -> int:
        """Create a request."""

    async def async_create_minimal_request(
        self,
        *,
        type_: str = "url",
        status: RequestStatus = RequestStatus.PENDING,
        correlation_id: str | None = None,
        chat_id: int | None = None,
        user_id: int | None = None,
        input_url: str | None = None,
        normalized_url: str | None = None,
        dedupe_hash: str | None = None,
    ) -> tuple[int, bool]:
        """Create a minimal request row."""

    async def async_get_request_by_forward(
        self, chat_id: int, fwd_message_id: int
    ) -> dict[str, Any] | None:
        """Return request by forward source identifiers."""

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Update request status."""

    async def async_update_request_status_with_correlation(
        self,
        request_id: int,
        status: str,
        correlation_id: str | None,
    ) -> None:
        """Update request status and correlation ID."""

    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None:
        """Update detected language."""

    async def async_update_request_correlation_id(
        self,
        request_id: int,
        correlation_id: str,
    ) -> None:
        """Update correlation ID."""

    async def async_update_request_error(
        self,
        request_id: int,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        error_context_json: Any | None = None,
    ) -> None:
        """Persist structured request error details."""

    async def async_get_request_error_context(self, request_id: int) -> dict[str, Any] | None:
        """Return structured request error context."""

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return all request rows for sync operations."""

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version for requests owned by *user_id*."""


@runtime_checkable
class CrawlResultRepositoryPort(Protocol):
    """Port for crawl-result query operations."""

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Return crawl result by request ID."""

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return all crawl rows for sync operations."""

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version for crawl results owned by *user_id*."""


@runtime_checkable
class LLMRepositoryPort(Protocol):
    """Port for LLM-call query operations."""

    async def async_get_llm_calls_by_request(self, request_id: int) -> list[dict[str, Any]]:
        """Return LLM calls by request ID."""

    async def async_count_llm_calls_by_request(self, request_id: int) -> int:
        """Return the number of LLM calls by request ID."""

    async def async_insert_llm_call(self, record: LLMCallRecord) -> int:
        """Persist an LLM call."""

    async def async_insert_llm_calls_batch(self, calls: list[dict[str, Any]]) -> list[int]:
        """Persist a batch of LLM calls."""

    async def async_get_latest_llm_model_by_request_id(self, request_id: int) -> str | None:
        """Return the latest model used for a request."""

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Return all LLM rows for sync operations."""

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version for LLM calls owned by *user_id*."""


@runtime_checkable
class TopicSearchRepositoryPort(Protocol):
    """Port for topic search query operations."""

    async def async_fts_search_paginated(
        self, query: str, *, limit: int = 20, offset: int = 0, user_id: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute paginated FTS query, scoped to user_id when provided."""

    async def async_search_request_ids(
        self,
        query: str,
        *,
        candidate_limit: int = 100,
    ) -> list[int] | None:
        """Return request IDs matching the topic query."""

    async def async_search_documents(self, query: str, *, limit: int) -> list[Any]:
        """Return indexed topic-search documents."""

    async def async_scan_documents(
        self,
        *,
        terms: list[str],
        normalized_query: str,
        seen_urls: set[str],
        limit: int,
        max_scan: int,
    ) -> list[Any]:
        """Return fallback-scanned topic-search documents."""


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
class VideoDownloadRepositoryPort(Protocol):
    async def async_get_video_download_by_request(
        self,
        request_id: int,
    ) -> dict[str, Any] | None:
        """Return video-download record by request ID."""

    async def async_create_video_download(
        self,
        request_id: int,
        video_id: str,
        status: str = "pending",
    ) -> int:
        """Create a video-download row."""

    async def async_update_video_download(self, download_id: int, **kwargs: Any) -> None:
        """Update a video-download row."""

    async def async_update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at: Any | None = None,
    ) -> None:
        """Update video-download status."""


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
class EmbeddingRepositoryPort(Protocol):
    async def async_get_all_embeddings(self) -> list[dict[str, Any]]:
        """Return all summary embeddings."""

    async def async_get_embeddings_by_request_ids(
        self,
        request_ids: list[int],
    ) -> list[dict[str, Any]]:
        """Return embeddings for selected request IDs."""

    async def async_get_recent_embeddings(self, *, limit: int) -> list[dict[str, Any]]:
        """Return recent embeddings."""

    async def async_create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Upsert a summary embedding."""

    async def async_get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Return summary embedding by summary ID."""
