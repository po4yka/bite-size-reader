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

    from app.application.dto.audio_generation import StoredAudioFileDTO
    from app.application.dto.import_bookmarks import BookmarkImportItemResult
    from app.application.dto.rule_execution import RuleEvaluationContextDTO
    from app.application.dto.vector_search import VectorSearchHitDTO
    from app.domain.services.import_parsers.base import ImportedBookmark


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

    async def async_update_bot_reply_message_id(
        self, request_id: int, bot_reply_message_id: int
    ) -> None:
        """Persist the Telegram message-id of the bot's reply for a request."""


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


@runtime_checkable
class VectorSearchPort(Protocol):
    async def search(
        self,
        query: str,
        *,
        correlation_id: str | None = None,
    ) -> list[VectorSearchHitDTO]:
        """Return vector-search hits for the query."""


@runtime_checkable
class EmbeddingProviderPort(Protocol):
    async def generate_embedding(
        self,
        text: str,
        *,
        language: str | None = None,
        task_type: str = "document",
    ) -> list[float]:
        """Generate an embedding vector."""

    def serialize_embedding(self, embedding: list[float]) -> bytes:
        """Serialize the embedding for persistence."""

    def get_model_name(self, language: str | None = None) -> str:
        """Return the effective model name for the requested language."""


@runtime_checkable
class TTSProviderPort(Protocol):
    async def synthesize(self, text: str, *, use_long_form: bool = False) -> bytes:
        """Synthesize speech for the provided text."""

    async def close(self) -> None:
        """Release provider resources."""


@runtime_checkable
class AudioStoragePort(Protocol):
    async def save_audio(self, summary_id: int, audio_bytes: bytes) -> StoredAudioFileDTO:
        """Persist synthesized audio and return its storage metadata."""


@runtime_checkable
class AudioGenerationRepositoryPort(Protocol):
    async def async_get_completed_generation(
        self,
        summary_id: int,
        source_field: str,
    ) -> dict[str, Any] | None:
        """Return a completed generation for the summary/source pair."""

    async def async_get_latest_generation(self, summary_id: int) -> dict[str, Any] | None:
        """Return the latest generation row for a summary."""

    async def async_mark_generation_started(
        self,
        *,
        summary_id: int,
        source_field: str,
        voice_id: str,
        model_name: str,
        language: str | None,
        char_count: int,
    ) -> None:
        """Create or update a generation row in generating state."""

    async def async_mark_generation_completed(
        self,
        *,
        summary_id: int,
        source_field: str,
        file_path: str,
        file_size_bytes: int,
        char_count: int,
        latency_ms: int,
    ) -> None:
        """Persist a completed generation result."""

    async def async_mark_generation_failed(
        self,
        *,
        summary_id: int,
        source_field: str,
        error_text: str,
        latency_ms: int,
    ) -> None:
        """Persist a failed generation result."""


@runtime_checkable
class WebhookRepositoryPort(Protocol):
    """Port for webhook subscription and delivery operations."""

    async def async_get_user_subscriptions(
        self, user_id: int, enabled_only: bool = True
    ) -> list[dict[str, Any]]:
        """Return webhook subscriptions for a user."""

    async def async_get_subscription_by_id(self, subscription_id: int) -> dict[str, Any] | None:
        """Return a single subscription by ID."""

    async def async_create_subscription(
        self,
        user_id: int,
        name: str | None,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Create a new webhook subscription."""

    async def async_update_subscription(
        self, subscription_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Update an existing webhook subscription."""

    async def async_delete_subscription(self, subscription_id: int) -> None:
        """Delete a webhook subscription."""

    async def async_log_delivery(
        self,
        subscription_id: int,
        event_type: str,
        payload: dict[str, Any],
        response_status: int | None,
        response_body: str | None,
        duration_ms: int | None,
        success: bool,
        attempt: int,
        error: str | None,
    ) -> dict[str, Any]:
        """Persist a webhook delivery attempt."""

    async def async_get_deliveries(
        self, subscription_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return delivery log entries for a subscription."""

    async def async_increment_failure_count(self, subscription_id: int) -> int:
        """Increment consecutive failure count. Returns the new count."""

    async def async_reset_failure_count(self, subscription_id: int) -> None:
        """Reset consecutive failure count to zero."""

    async def async_disable_subscription(self, subscription_id: int) -> None:
        """Disable a webhook subscription."""

    async def async_rotate_secret(self, subscription_id: int, new_secret: str) -> None:
        """Rotate the HMAC secret for a subscription."""


@runtime_checkable
class TagRepositoryPort(Protocol):
    """Port for tag CRUD and summary-tag association operations."""

    async def async_get_user_tags(self, user_id: int) -> list[dict[str, Any]]:
        """Return all tags owned by a user."""

    async def async_get_tag_by_id(self, tag_id: int) -> dict[str, Any] | None:
        """Return tag by ID."""

    async def async_create_tag(
        self,
        user_id: int,
        name: str,
        normalized_name: str,
        color: str | None,
    ) -> dict[str, Any]:
        """Create a tag and return the created record."""

    async def async_update_tag(
        self,
        tag_id: int,
        name: str | None,
        color: str | None,
    ) -> dict[str, Any]:
        """Update a tag and return the updated record."""

    async def async_delete_tag(self, tag_id: int) -> None:
        """Delete a tag."""

    async def async_attach_tag(
        self,
        summary_id: int,
        tag_id: int,
        source: str,
    ) -> dict[str, Any]:
        """Attach a tag to a summary and return the association record."""

    async def async_detach_tag(self, summary_id: int, tag_id: int) -> None:
        """Detach a tag from a summary."""

    async def async_get_tags_for_summary(self, summary_id: int) -> list[dict[str, Any]]:
        """Return all tags attached to a summary."""

    async def async_merge_tags(self, source_tag_ids: list[int], target_tag_id: int) -> None:
        """Merge source tags into target tag, reassigning all associations."""

    async def async_get_tag_by_normalized_name(
        self,
        user_id: int,
        normalized_name: str,
    ) -> dict[str, Any] | None:
        """Return tag by normalized name within a user scope."""


@runtime_checkable
class BookmarkImportPort(Protocol):
    async def async_import_bookmark(
        self,
        bookmark: ImportedBookmark,
        *,
        user_id: int,
        options: dict[str, Any],
    ) -> BookmarkImportItemResult:
        """Import a single bookmark transactionally."""


@runtime_checkable
class CollectionMembershipPort(Protocol):
    async def async_add_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        """Add a summary to a collection owned by the user."""

    async def async_remove_summary(
        self,
        *,
        user_id: int,
        collection_id: int,
        summary_id: int,
    ) -> str:
        """Remove a summary from a collection owned by the user."""


@runtime_checkable
class RuleContextPort(Protocol):
    async def async_build_context(self, event_data: dict[str, Any]) -> RuleEvaluationContextDTO:
        """Build a rule-evaluation context from event data."""


@runtime_checkable
class WebhookDispatchPort(Protocol):
    async def async_dispatch(self, url: str, payload: dict[str, Any]) -> int:
        """Dispatch a webhook payload and return the response status code."""


@runtime_checkable
class RuleRateLimiterPort(Protocol):
    async def async_allow_execution(
        self,
        user_id: int,
        *,
        limit: int,
        window_seconds: float,
    ) -> bool:
        """Return True when the rule execution should proceed."""


@runtime_checkable
class RuleRepositoryPort(Protocol):
    """Port for automation rule CRUD and execution log operations."""

    async def async_get_user_rules(
        self, user_id: int, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        """Return all non-deleted rules owned by a user."""

    async def async_get_rule_by_id(self, rule_id: int) -> dict[str, Any] | None:
        """Return rule by ID."""

    async def async_get_rules_by_event_type(
        self, user_id: int, event_type: str
    ) -> list[dict[str, Any]]:
        """Return enabled rules matching event type, ordered by priority."""

    async def async_create_rule(
        self,
        user_id: int,
        name: str,
        event_type: str,
        conditions: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        match_mode: str = "all",
        priority: int = 0,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a rule and return the created record."""

    async def async_update_rule(self, rule_id: int, **fields: Any) -> dict[str, Any]:
        """Update provided fields on a rule and return the updated record."""

    async def async_soft_delete_rule(self, rule_id: int) -> None:
        """Soft-delete a rule."""

    async def async_increment_run_count(self, rule_id: int) -> None:
        """Increment run_count and set last_triggered_at to now."""

    async def async_create_execution_log(
        self,
        rule_id: int,
        summary_id: int | None,
        event_type: str,
        matched: bool,
        conditions_result: list[dict[str, Any]] | None = None,
        actions_taken: list[dict[str, Any]] | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        """Insert an execution log entry and return the created record."""

    async def async_get_execution_logs(
        self, rule_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return paginated execution logs for a rule."""


@runtime_checkable
class ImportJobRepositoryPort(Protocol):
    """Port for import job tracking operations."""

    async def async_create_job(
        self,
        user_id: int,
        source_format: str,
        file_name: str | None,
        total_items: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Insert a new ImportJob and return the created record."""

    async def async_get_job(self, job_id: int) -> dict[str, Any] | None:
        """Return a single import job by ID."""

    async def async_list_jobs(self, user_id: int) -> list[dict[str, Any]]:
        """List user's import jobs, ordered by created_at DESC."""

    async def async_update_progress(
        self,
        job_id: int,
        processed: int,
        created: int,
        skipped: int,
        failed: int,
        errors: list[str] | None = None,
    ) -> None:
        """Update import job progress counters."""

    async def async_set_status(self, job_id: int, status: str) -> None:
        """Update the status field of an import job."""

    async def async_delete_job(self, job_id: int) -> None:
        """Hard delete an import job."""


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
