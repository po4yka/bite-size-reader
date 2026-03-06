"""Adapter-facing repository protocols and SQLite factory bindings.

Adapters depend on these protocol contracts instead of importing concrete
SQLite repositories directly. Concrete adapters are wired here (composition seam).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager


class RequestRepositoryPort(Protocol):
    async def async_create_request(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None: ...
    async def async_get_request_by_forward(
        self, cid: int, fwd_message_id: int
    ) -> dict[str, Any] | None: ...
    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None: ...
    async def async_create_minimal_request(self, *args: Any, **kwargs: Any) -> tuple[int, bool]: ...
    async def async_update_request_status(self, request_id: int, status: str) -> None: ...
    async def async_update_request_lang_detected(self, request_id: int, lang: str) -> None: ...
    async def async_update_request_correlation_id(
        self, request_id: int, correlation_id: str
    ) -> None: ...
    async def async_update_request_error(self, request_id: int, error: str) -> None: ...


class SummaryRepositoryPort(Protocol):
    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None: ...
    async def async_get_unread_summary_by_request_id(
        self, request_id: int
    ) -> dict[str, Any] | None: ...
    async def async_get_summaries_by_request_ids(
        self, request_ids: list[int]
    ) -> dict[int, dict[str, Any]]: ...
    async def async_update_summary_insights(
        self, summary_id: int, insights_json: dict[str, Any]
    ) -> None: ...
    async def async_upsert_summary(
        self,
        request_id: int,
        lang: str,
        json_payload: dict[str, Any],
        insights_json: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> int: ...


class UserRepositoryPort(Protocol):
    async def async_insert_user_interaction(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_upsert_user(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_upsert_chat(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None: ...
    async def async_update_user_preferences(
        self, telegram_user_id: int, preferences: dict[str, Any]
    ) -> None: ...


class LLMRepositoryPort(Protocol):
    async def async_insert_llm_call(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_get_latest_llm_model_by_request_id(self, request_id: int) -> str | None: ...


class CrawlResultRepositoryPort(Protocol):
    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None: ...


class VideoDownloadRepositoryPort(Protocol):
    async def async_get_video_download_by_request(
        self, request_id: int
    ) -> dict[str, Any] | None: ...
    async def async_create_video_download(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_update_video_download(self, download_id: int, **kwargs: Any) -> None: ...
    async def async_update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at: Any | None = None,
    ) -> None: ...


class AuditLogRepositoryPort(Protocol):
    async def async_insert_audit_log(self, *args: Any, **kwargs: Any) -> int: ...


class BatchSessionRepositoryPort(Protocol):
    async def async_create_batch_session(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_add_batch_session_item(self, *args: Any, **kwargs: Any) -> int: ...
    async def async_get_batch_session_items(self, session_id: int) -> list[dict[str, Any]]: ...
    async def async_update_batch_session_status(self, *args: Any, **kwargs: Any) -> None: ...
    async def async_update_batch_session_counts(self, *args: Any, **kwargs: Any) -> None: ...
    async def async_update_batch_session_relationship(self, *args: Any, **kwargs: Any) -> None: ...
    async def async_update_batch_session_combined_summary(
        self, *args: Any, **kwargs: Any
    ) -> None: ...
    async def async_update_batch_session_item_series_info(
        self, *args: Any, **kwargs: Any
    ) -> None: ...


class KarakeepSyncRepositoryPort(Protocol):
    async def async_delete_all_sync_records(self) -> int: ...


def create_request_repository(db: DatabaseSessionManager) -> RequestRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.request_repository import (
        SqliteRequestRepositoryAdapter,
    )

    return SqliteRequestRepositoryAdapter(db)


def create_summary_repository(db: DatabaseSessionManager) -> SummaryRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
        SqliteSummaryRepositoryAdapter,
    )

    return SqliteSummaryRepositoryAdapter(db)


def create_user_repository(db: DatabaseSessionManager) -> UserRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )

    return SqliteUserRepositoryAdapter(db)


def create_llm_repository(db: DatabaseSessionManager) -> LLMRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
        SqliteLLMRepositoryAdapter,
    )

    return SqliteLLMRepositoryAdapter(db)


def create_crawl_result_repository(db: DatabaseSessionManager) -> CrawlResultRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
        SqliteCrawlResultRepositoryAdapter,
    )

    return SqliteCrawlResultRepositoryAdapter(db)


def create_video_download_repository(db: DatabaseSessionManager) -> VideoDownloadRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.video_download_repository import (
        SqliteVideoDownloadRepositoryAdapter,
    )

    return SqliteVideoDownloadRepositoryAdapter(db)


def create_audit_log_repository(db: DatabaseSessionManager) -> AuditLogRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
        SqliteAuditLogRepositoryAdapter,
    )

    return SqliteAuditLogRepositoryAdapter(db)


def create_batch_session_repository(db: DatabaseSessionManager) -> BatchSessionRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.batch_session_repository import (
        SqliteBatchSessionRepositoryAdapter,
    )

    return SqliteBatchSessionRepositoryAdapter(db)


def create_karakeep_sync_repository(db: DatabaseSessionManager) -> KarakeepSyncRepositoryPort:
    from app.infrastructure.persistence.sqlite.repositories.karakeep_sync_repository import (
        SqliteKarakeepSyncRepositoryAdapter,
    )

    return SqliteKarakeepSyncRepositoryAdapter(db)
