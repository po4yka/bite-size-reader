"""Backward-compatible database facade.

**Deprecated** -- prefer ``DatabaseSessionManager`` + repository adapters for
new code.  This module is retained solely so that existing call-sites and tests
continue to work without modification.

Migration path
--------------
1. ``DatabaseSessionManager``  (``app.db.session``)   -- connections, locks,
   migrations, backup, raw SQL.
2. Repository adapters (``app.infrastructure.persistence.sqlite.repositories``)
   -- per-entity async CRUD.

This facade creates a ``DatabaseSessionManager`` internally and delegates all
infrastructure work to it.  Sync ORM helpers are kept as thin wrappers for
backward compatibility.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import warnings
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import peewee

from app.core.time_utils import UTC
from app.db.database_diagnostics import DatabaseDiagnostics
from app.db.database_maintenance import DatabaseMaintenance
from app.db.json_utils import (
    decode_json_field,
    normalize_json_container,
    normalize_legacy_json_value,
    prepare_json_payload,
)
from app.db.models import (
    ALL_MODELS,
    AuditLog,
    Chat,
    CrawlResult,
    LLMCall,
    Request,
    Summary,
    SummaryEmbedding,
    TelegramMessage,
    User,
    UserInteraction,
    model_to_dict,
)
from app.db.session import DatabaseSessionManager
from app.db.topic_search_index import TopicSearchIndexManager
from app.db.video_downloads import VideoDownloadManager
from app.services.topic_search_utils import (
    ensure_mapping,
    summary_matches_topic,
    yield_topic_fragments,
)
from app.services.trending_cache import clear_trending_cache

if TYPE_CHECKING:
    import sqlite3

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None

# Default database operation timeout in seconds
# Prevents indefinite hangs on lock acquisition or slow operations
# Can be overridden via DB_OPERATION_TIMEOUT environment variable
DB_OPERATION_TIMEOUT = 30.0

# Default maximum retries for transient database errors
# Can be overridden via DB_MAX_RETRIES environment variable
DB_MAX_RETRIES = 3

# Default JSON validation limits
# Can be overridden via DB_JSON_* environment variables
DB_JSON_MAX_SIZE = 10_000_000  # 10MB
DB_JSON_MAX_DEPTH = 20
DB_JSON_MAX_ARRAY_LENGTH = 10_000
DB_JSON_MAX_DICT_KEYS = 1_000


@dataclass
class Database:
    """Peewee-backed database facade providing backward-compatible access.

    .. deprecated::
        Use ``DatabaseSessionManager`` + repository adapters instead.

    This class creates a ``DatabaseSessionManager`` internally and delegates
    infrastructure operations to it while keeping sync ORM helpers for
    backward compatibility with existing tests and call-sites.
    """

    path: str
    _logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    # Managed by __post_init__ -- not user-supplied
    _mgr: DatabaseSessionManager = field(init=False, repr=False)
    _database: peewee.SqliteDatabase = field(init=False, repr=False)
    _diagnostics: DatabaseDiagnostics = field(init=False, repr=False)
    _maintenance: DatabaseMaintenance = field(init=False, repr=False)
    _topic_search: TopicSearchIndexManager = field(init=False, repr=False)
    _video_downloads: VideoDownloadManager = field(init=False, repr=False)

    # Configuration values (can be set via database_config parameter or use module defaults)
    operation_timeout: float = field(default=DB_OPERATION_TIMEOUT)
    max_retries: int = field(default=DB_MAX_RETRIES)
    json_max_size: int = field(default=DB_JSON_MAX_SIZE)
    json_max_depth: int = field(default=DB_JSON_MAX_DEPTH)
    json_max_array_length: int = field(default=DB_JSON_MAX_ARRAY_LENGTH)
    json_max_dict_keys: int = field(default=DB_JSON_MAX_DICT_KEYS)

    def __post_init__(self) -> None:
        warnings.warn(
            "Database is deprecated; use DatabaseSessionManager + repository adapters",
            DeprecationWarning,
            stacklevel=2,
        )
        self._mgr = DatabaseSessionManager(
            path=self.path,
            _logger=self._logger,
            operation_timeout=self.operation_timeout,
            max_retries=self.max_retries,
            json_max_size=self.json_max_size,
            json_max_depth=self.json_max_depth,
            json_max_array_length=self.json_max_array_length,
            json_max_dict_keys=self.json_max_dict_keys,
        )
        self._database = self._mgr.database
        self._diagnostics = DatabaseDiagnostics(self, self._database, self._logger)
        self._maintenance = DatabaseMaintenance(self._database, self.path, self._logger)
        self._topic_search = TopicSearchIndexManager(self._database, self._logger)
        self._video_downloads = VideoDownloadManager(self._logger)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def database(self) -> peewee.SqliteDatabase:
        """Access the underlying Peewee database instance."""
        return self._database

    # ------------------------------------------------------------------
    # Infrastructure -- delegated to DatabaseSessionManager
    # ------------------------------------------------------------------

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_operation",
        read_only: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Execute database operation with timeout and retry protection.

        Delegates to ``DatabaseSessionManager._safe_db_operation``.
        """
        return await self._mgr._safe_db_operation(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            read_only=read_only,
            **kwargs,
        )

    async def _safe_db_transaction(
        self,
        operation: Any,
        *args: Any,
        timeout: float | None = None,
        operation_name: str = "database_transaction",
        **kwargs: Any,
    ) -> Any:
        """Execute database operation within an explicit transaction.

        Delegates to ``DatabaseSessionManager._safe_db_transaction``.
        """
        return await self._mgr._safe_db_transaction(
            operation,
            *args,
            timeout=timeout,
            operation_name=operation_name,
            **kwargs,
        )

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a context manager yielding the raw sqlite3 connection."""
        with self._mgr.connect() as conn:
            yield conn

    def migrate(self) -> None:
        """Create tables, run versioned migrations, and perform startup maintenance.

        Delegates table creation, migrations, and JSON coercion to the session
        manager, then runs topic-search index rebuild and maintenance locally
        (these depend on helpers that live on this class).
        """
        with self._database.connection_context(), self._database.bind_ctx(ALL_MODELS):
            self._database.create_tables(ALL_MODELS, safe=True)

            # Run versioned migrations (column additions, data migrations).
            # Must stay inside the same connection_context to preserve tables
            # on :memory: databases.
            from app.cli.migrations.migration_runner import MigrationRunner

            runner = MigrationRunner(self)
            runner.run_pending()

            # Idempotent JSON coercion (runs every startup)
            from app.db.schema_migrator import SchemaMigrator

            SchemaMigrator(self._database, self._logger).ensure_schema_compatibility()

            # Topic search FTS index
            self._topic_search.ensure_index()

        self._run_database_maintenance()
        self._logger.info("db_migrated", extra={"path": self.path})

    def create_backup_copy(self, dest_path: str) -> Path:
        """Create a full backup of the database file."""
        return self._mgr.create_backup_copy(dest_path)

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        """Execute raw SQL synchronously."""
        self._mgr.execute(sql, params)

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        """Fetch a single row using raw SQL."""
        return self._mgr.fetchone(sql, params)

    # ------------------------------------------------------------------
    # JSON utilities -- static delegates kept for backward compat
    # ------------------------------------------------------------------

    _normalize_json_container = staticmethod(normalize_json_container)
    _prepare_json_payload = staticmethod(prepare_json_payload)
    _normalize_legacy_json_value = staticmethod(normalize_legacy_json_value)

    def _decode_json_field(self, value: Any) -> tuple[Any | None, str | None]:
        """Decode JSON field with security validation.

        Delegates to ``app.db.json_utils.decode_json_field`` with instance config.
        """
        return decode_json_field(
            value,
            max_size=self.json_max_size,
            max_depth=self.json_max_depth,
            max_array_length=self.json_max_array_length,
            max_dict_keys=self.json_max_dict_keys,
        )

    # ------------------------------------------------------------------
    # Diagnostics / maintenance delegates
    # ------------------------------------------------------------------

    def get_database_overview(self) -> dict[str, Any]:
        return self._diagnostics.get_database_overview()

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        return self._diagnostics.verify_processing_integrity(
            required_fields=required_fields,
            limit=limit,
        )

    def _run_database_maintenance(self) -> None:
        """Run database maintenance operations (ANALYZE, VACUUM)."""
        self._maintenance.run_maintenance()

    def _run_analyze(self) -> None:
        """Run ANALYZE to update query planner statistics."""
        self._maintenance.run_analyze()

    def _run_vacuum(self) -> None:
        """Run VACUUM to reclaim disk space and defragment."""
        self._maintenance.run_vacuum()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mask_path(self, path: str) -> str:
        try:
            p = Path(path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except (OSError, ValueError, AttributeError):
            return "..."

    @staticmethod
    def _convert_bool_fields(data: dict[str, Any], fields: Iterable[str]) -> None:
        for field_name in fields:
            if field_name in data and data[field_name] is not None:
                data[field_name] = int(bool(data[field_name]))

    # Topic search helpers -- static delegates for backward compat
    _yield_topic_fragments = staticmethod(yield_topic_fragments)
    _summary_matches_topic = staticmethod(summary_matches_topic)

    # ------------------------------------------------------------------
    # User / Chat upserts
    # ------------------------------------------------------------------

    def upsert_user(
        self, *, telegram_user_id: int, username: str | None = None, is_owner: bool = False
    ) -> None:
        User.insert(
            telegram_user_id=telegram_user_id,
            username=username,
            is_owner=is_owner,
        ).on_conflict(
            conflict_target=[User.telegram_user_id],
            update={"username": username, "is_owner": is_owner},
        ).execute()

    def upsert_chat(
        self,
        *,
        chat_id: int,
        type_: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
        Chat.insert(
            chat_id=chat_id,
            type=type_,
            title=title,
            username=username,
        ).on_conflict(
            conflict_target=[Chat.chat_id],
            update={
                "type": type_,
                "title": title,
                "username": username,
            },
        ).execute()

    # ------------------------------------------------------------------
    # User interaction CRUD
    # ------------------------------------------------------------------

    def insert_user_interaction(
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
        created = UserInteraction.create(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            interaction_type=interaction_type,
            command=command,
            input_text=input_text,
            input_url=input_url,
            has_forward=has_forward,
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            media_type=media_type,
            correlation_id=correlation_id,
            structured_output_enabled=structured_output_enabled,
        )
        self._logger.debug(
            "db_user_interaction_inserted",
            extra={
                "interaction_id": created.id,
                "user_id": user_id,
                "interaction_type": interaction_type,
            },
        )
        return created.id

    def update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        legacy_fields = (
            response_sent,
            response_type,
            error_occurred,
            error_message,
            processing_time_ms,
            request_id,
        )
        if updates and any(f is not None for f in legacy_fields):
            msg = "Cannot mix explicit field arguments with the updates mapping"
            raise ValueError(msg)

        update_values: dict[Any, Any] = {}
        if updates:
            invalid_fields = [
                key
                for key in updates
                if not isinstance(getattr(UserInteraction, key, None), peewee.Field)
            ]
            if invalid_fields:
                msg = f"Unknown user interaction fields: {', '.join(invalid_fields)}"
                raise ValueError(msg)
            for key, value in updates.items():
                field_obj = getattr(UserInteraction, key)
                update_values[field_obj] = value

        if response_sent is not None:
            update_values[UserInteraction.response_sent] = response_sent
        if response_type is not None:
            update_values[UserInteraction.response_type] = response_type
        if error_occurred is not None:
            update_values[UserInteraction.error_occurred] = error_occurred
        if error_message is not None:
            update_values[UserInteraction.error_message] = error_message
        if processing_time_ms is not None:
            update_values[UserInteraction.processing_time_ms] = processing_time_ms
        if request_id is not None:
            update_values[UserInteraction.request] = request_id

        if not update_values:
            return

        updated_at_field = getattr(UserInteraction, "updated_at", None)
        if isinstance(updated_at_field, peewee.Field):
            try:
                columns = {
                    column.name
                    for column in self._database.get_columns(UserInteraction._meta.table_name)
                }
            except (peewee.DatabaseError, AttributeError):
                columns = set()
            if updated_at_field.column_name in columns:
                update_values[updated_at_field] = dt.datetime.now(UTC)

        with self._database.connection_context():
            UserInteraction.update(update_values).where(
                UserInteraction.id == interaction_id
            ).execute()

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> None:
        """Async wrapper for :meth:`update_user_interaction`."""
        await self._safe_db_operation(
            self.update_user_interaction,
            interaction_id,
            updates=updates,
            operation_name="update_user_interaction",
            **fields,
        )

    def get_user_interactions(
        self,
        *,
        uid: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent user interactions for a user."""
        interactions = (
            UserInteraction.select()
            .where(UserInteraction.user_id == uid)
            .order_by(UserInteraction.created_at.desc())
            .limit(limit)
        )
        return [model_to_dict(interaction) for interaction in interactions]

    # ------------------------------------------------------------------
    # Request CRUD
    # ------------------------------------------------------------------

    def create_request(
        self,
        *,
        type_: str,
        status: str,
        correlation_id: str | None,
        chat_id: int | None,
        user_id: int | None,
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
        try:
            request = Request.create(
                type=type_,
                status=status,
                correlation_id=correlation_id,
                chat_id=chat_id,
                user_id=user_id,
                input_url=input_url,
                normalized_url=normalized_url,
                dedupe_hash=dedupe_hash,
                input_message_id=input_message_id,
                fwd_from_chat_id=fwd_from_chat_id,
                fwd_from_msg_id=fwd_from_msg_id,
                lang_detected=lang_detected,
                content_text=content_text,
                route_version=route_version,
            )
            return request.id
        except peewee.IntegrityError:
            if dedupe_hash:
                Request.update(
                    {
                        Request.correlation_id: correlation_id,
                        Request.status: status,
                        Request.chat_id: chat_id,
                        Request.user_id: user_id,
                        Request.input_url: input_url,
                        Request.normalized_url: normalized_url,
                        Request.input_message_id: input_message_id,
                        Request.fwd_from_chat_id: fwd_from_chat_id,
                        Request.fwd_from_msg_id: fwd_from_msg_id,
                        Request.lang_detected: lang_detected,
                        Request.content_text: content_text,
                        Request.route_version: route_version,
                    }
                ).where(Request.dedupe_hash == dedupe_hash).execute()
                existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
                if existing:
                    return existing.id
            raise

    def get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
        return model_to_dict(request)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_request_by_dedupe_hash`."""
        return await self._safe_db_operation(
            self.get_request_by_dedupe_hash,
            dedupe_hash,
            operation_name="get_request_by_dedupe_hash",
            read_only=True,
        )

    def get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.id == request_id)
        return model_to_dict(request)

    async def async_get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_request_by_id`."""
        return await self._safe_db_operation(
            self.get_request_by_id,
            request_id,
            operation_name="get_request_by_id",
            read_only=True,
        )

    def get_request_by_forward(
        self,
        fwd_chat_id: int,
        fwd_msg_id: int,
    ) -> dict[str, Any] | None:
        request = Request.get_or_none(
            (Request.fwd_from_chat_id == fwd_chat_id) & (Request.fwd_from_msg_id == fwd_msg_id)
        )
        return model_to_dict(request)

    def update_request_status(self, request_id: int, status: str) -> None:
        with self._database.connection_context():
            Request.update({Request.status: status}).where(Request.id == request_id).execute()

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Asynchronously update the request status."""
        await self._safe_db_operation(
            self.update_request_status,
            request_id,
            status,
            operation_name="update_request_status",
        )

    def update_request_status_with_correlation(
        self, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        update_map: dict[Any, Any] = {Request.status: status}
        if correlation_id:
            update_map[Request.correlation_id] = correlation_id
        with self._database.connection_context():
            Request.update(update_map).where(Request.id == request_id).execute()

    async def async_update_request_status_with_correlation(
        self, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        """Asynchronously update request status and correlation_id together."""
        await self._safe_db_operation(
            self.update_request_status_with_correlation,
            request_id,
            status,
            correlation_id,
            operation_name="update_request_status_with_correlation",
        )

    def update_request_correlation_id(self, request_id: int, correlation_id: str) -> None:
        with self._database.connection_context():
            Request.update({Request.correlation_id: correlation_id}).where(
                Request.id == request_id
            ).execute()

    def update_request_lang_detected(self, request_id: int, lang: str | None) -> None:
        with self._database.connection_context():
            Request.update({Request.lang_detected: lang}).where(Request.id == request_id).execute()

    # ------------------------------------------------------------------
    # Crawl result CRUD
    # ------------------------------------------------------------------

    def get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        result = CrawlResult.get_or_none(CrawlResult.request == request_id)
        data = model_to_dict(result)
        if data:
            self._convert_bool_fields(data, ["firecrawl_success"])
        return data

    async def async_get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_crawl_result_by_request`."""
        return await self._safe_db_operation(
            self.get_crawl_result_by_request,
            request_id,
            operation_name="get_crawl_result_by_request",
            read_only=True,
        )

    def insert_crawl_result(
        self,
        *,
        request_id: int,
        source_url: str | None,
        endpoint: str | None,
        http_status: int | None,
        status: str | None,
        options_json: JSONValue,
        correlation_id: str | None,
        content_markdown: str | None,
        content_html: str | None,
        structured_json: JSONValue,
        metadata_json: JSONValue,
        links_json: JSONValue,
        screenshots_paths_json: JSONValue,
        firecrawl_success: bool | None,
        firecrawl_error_code: str | None,
        firecrawl_error_message: str | None,
        firecrawl_details_json: JSONValue,
        raw_response_json: JSONValue,
        latency_ms: int | None,
        error_text: str | None,
    ) -> int:
        try:
            result = CrawlResult.create(
                request=request_id,
                source_url=source_url,
                endpoint=endpoint,
                http_status=http_status,
                status=status,
                options_json=self._prepare_json_payload(options_json, default={}),
                correlation_id=correlation_id,
                content_markdown=content_markdown,
                content_html=content_html,
                structured_json=self._prepare_json_payload(structured_json, default={}),
                metadata_json=self._prepare_json_payload(metadata_json, default={}),
                links_json=self._prepare_json_payload(links_json, default={}),
                screenshots_paths_json=self._prepare_json_payload(screenshots_paths_json),
                firecrawl_success=firecrawl_success,
                firecrawl_error_code=firecrawl_error_code,
                firecrawl_error_message=firecrawl_error_message,
                firecrawl_details_json=self._prepare_json_payload(firecrawl_details_json),
                raw_response_json=self._prepare_json_payload(raw_response_json),
                latency_ms=latency_ms,
                error_text=error_text,
            )
            return result.id
        except peewee.IntegrityError:
            existing = CrawlResult.get_or_none(CrawlResult.request == request_id)
            if existing:
                return existing.id
            raise

    # ------------------------------------------------------------------
    # Telegram message CRUD
    # ------------------------------------------------------------------

    def insert_telegram_message(
        self,
        *,
        request_id: int,
        message_id: int | None,
        chat_id: int | None,
        date_ts: int | None,
        text_full: str | None,
        entities_json: JSONValue,
        media_type: str | None,
        media_file_ids_json: JSONValue,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: JSONValue,
    ) -> int:
        try:
            message = TelegramMessage.create(
                request=request_id,
                message_id=message_id,
                chat_id=chat_id,
                date_ts=date_ts,
                text_full=text_full,
                entities_json=self._prepare_json_payload(entities_json),
                media_type=media_type,
                media_file_ids_json=self._prepare_json_payload(media_file_ids_json),
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_type=forward_from_chat_type,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                forward_date_ts=forward_date_ts,
                telegram_raw_json=self._prepare_json_payload(telegram_raw_json),
            )
            return message.id
        except peewee.IntegrityError:
            existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
            if existing:
                return existing.id
            raise

    # ------------------------------------------------------------------
    # LLM call CRUD
    # ------------------------------------------------------------------

    def insert_llm_call(
        self,
        *,
        request_id: int | None,
        provider: str | None,
        model: str | None,
        endpoint: str | None,
        request_headers_json: JSONValue,
        request_messages_json: JSONValue,
        response_text: str | None,
        response_json: JSONValue,
        tokens_prompt: int | None,
        tokens_completion: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
        status: str | None,
        error_text: str | None,
        structured_output_used: bool | None,
        structured_output_mode: str | None,
        error_context_json: JSONValue,
    ) -> int:
        headers_payload = self._prepare_json_payload(request_headers_json, default={})
        messages_payload = self._prepare_json_payload(request_messages_json, default=[])
        response_payload = self._prepare_json_payload(response_json, default={})
        error_context_payload = self._prepare_json_payload(error_context_json)
        payload: dict[Any, Any] = {
            LLMCall.request: request_id,
            LLMCall.provider: provider,
            LLMCall.model: model,
            LLMCall.endpoint: endpoint,
            LLMCall.request_headers_json: headers_payload,
            LLMCall.request_messages_json: messages_payload,
            LLMCall.tokens_prompt: tokens_prompt,
            LLMCall.tokens_completion: tokens_completion,
            LLMCall.cost_usd: cost_usd,
            LLMCall.latency_ms: latency_ms,
            LLMCall.status: status,
            LLMCall.error_text: error_text,
            LLMCall.structured_output_used: structured_output_used,
            LLMCall.structured_output_mode: structured_output_mode,
            LLMCall.error_context_json: error_context_payload,
        }
        if provider == "openrouter":
            payload[LLMCall.openrouter_response_text] = response_text
            payload[LLMCall.openrouter_response_json] = response_payload
            payload[LLMCall.response_text] = None
            payload[LLMCall.response_json] = None
        else:
            payload[LLMCall.response_text] = response_text
            payload[LLMCall.response_json] = response_payload

        call = LLMCall.create(**{field.name: value for field, value in payload.items()})
        return call.id

    async def async_insert_llm_call(self, **kwargs: Any) -> int:
        """Persist an LLM call without blocking the event loop."""
        return await self._safe_db_operation(
            self.insert_llm_call,
            operation_name="insert_llm_call",
            **kwargs,
        )

    def get_latest_llm_model_by_request_id(self, request_id: int) -> str | None:
        call = (
            LLMCall.select(LLMCall.model)
            .where(LLMCall.request == request_id, LLMCall.model.is_null(False))
            .order_by(LLMCall.id.desc())
            .first()
        )
        return call.model if call else None

    # ------------------------------------------------------------------
    # Summary CRUD
    # ------------------------------------------------------------------

    def get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        summary = Summary.get_or_none(Summary.request == request_id)
        data = model_to_dict(summary)
        if data:
            self._convert_bool_fields(data, ["is_read"])
        return data

    async def async_get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_summary_by_request`."""
        return await self._safe_db_operation(
            self.get_summary_by_request,
            request_id,
            operation_name="get_summary_by_request",
            read_only=True,
        )

    def get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Get a summary by its ID, including request_id."""
        summary = (
            Summary.select(Summary, Request).join(Request).where(Summary.id == summary_id).first()
        )
        if not summary:
            return None

        data = model_to_dict(summary)
        if data:
            if "request" in data:
                data["request_id"] = data["request"]
            self._convert_bool_fields(data, ["is_read"])
        return data

    async def async_get_summary_by_id(self, summary_id: int) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_summary_by_id`."""
        return await self._safe_db_operation(
            self.get_summary_by_id,
            summary_id,
            operation_name="get_summary_by_id",
            read_only=True,
        )

    def insert_summary(
        self,
        *,
        request_id: int,
        lang: str | None,
        json_payload: JSONValue,
        insights_json: JSONValue = None,
        version: int = 1,
        is_read: bool = False,
    ) -> int:
        summary = Summary.create(
            request=request_id,
            lang=lang,
            json_payload=self._prepare_json_payload(json_payload),
            insights_json=self._prepare_json_payload(insights_json),
            version=version,
            is_read=is_read,
        )
        self._topic_search.refresh_index(request_id)
        clear_trending_cache()
        return summary.id

    def upsert_summary(
        self,
        *,
        request_id: int,
        lang: str | None,
        json_payload: JSONValue,
        insights_json: JSONValue = None,
        is_read: bool | None = None,
    ) -> int:
        payload_value = self._prepare_json_payload(json_payload)
        insights_value = self._prepare_json_payload(insights_json)
        try:
            summary = Summary.create(
                request=request_id,
                lang=lang,
                json_payload=payload_value,
                insights_json=insights_value,
                version=1,
                is_read=is_read if is_read is not None else False,
            )
            self._topic_search.refresh_index(request_id)
            clear_trending_cache()
            return summary.version
        except peewee.IntegrityError:
            update_map: dict[Any, Any] = {
                Summary.lang: lang,
                Summary.json_payload: payload_value,
                Summary.version: Summary.version + 1,
                Summary.created_at: dt.datetime.now(UTC),
            }
            if insights_value is not None:
                update_map[Summary.insights_json] = insights_value
            if is_read is not None:
                update_map[Summary.is_read] = is_read
            query = Summary.update(update_map).where(Summary.request == request_id)
            query.execute()
            updated = Summary.get_or_none(Summary.request == request_id)
            version_val = updated.version if updated else 0
            self._topic_search.refresh_index(request_id)
            clear_trending_cache()
            return version_val

    async def async_upsert_summary(self, **kwargs: Any) -> int:
        """Asynchronously upsert a summary entry."""
        return await self._safe_db_operation(
            self.upsert_summary,
            operation_name="upsert_summary",
            **kwargs,
        )

    def update_summary_insights(self, request_id: int, insights_json: JSONValue) -> None:
        Summary.update({Summary.insights_json: self._prepare_json_payload(insights_json)}).where(
            Summary.request == request_id
        ).execute()

    def mark_summary_as_read_by_id(self, summary_id: int) -> None:
        """Mark a summary as read by its ID."""
        with self._database.connection_context():
            Summary.update({Summary.is_read: True}).where(Summary.id == summary_id).execute()

    async def async_mark_summary_as_read(self, summary_id: int) -> None:
        """Async wrapper for :meth:`mark_summary_as_read_by_id`."""
        await self._safe_db_operation(
            self.mark_summary_as_read_by_id,
            summary_id,
            operation_name="mark_summary_as_read",
        )

    def mark_summary_as_unread_by_id(self, summary_id: int) -> None:
        """Mark a summary as unread by its ID."""
        with self._database.connection_context():
            Summary.update({Summary.is_read: False}).where(Summary.id == summary_id).execute()

    async def async_mark_summary_as_unread(self, summary_id: int) -> None:
        """Async wrapper for :meth:`mark_summary_as_unread_by_id`."""
        await self._safe_db_operation(
            self.mark_summary_as_unread_by_id,
            summary_id,
            operation_name="mark_summary_as_unread",
        )

    def mark_summary_as_read(self, request_id: int) -> None:
        with self._database.connection_context():
            Summary.update({Summary.is_read: True}).where(Summary.request == request_id).execute()

    def get_read_status(self, request_id: int) -> bool:
        summary = Summary.get_or_none(Summary.request == request_id)
        return bool(summary.is_read) if summary else False

    # ------------------------------------------------------------------
    # Unread summaries (with topic search)
    # ------------------------------------------------------------------

    def get_unread_summaries(
        self,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return unread summary rows filtered by owner/chat/topic constraints."""
        if limit <= 0:
            return []

        topic_query = topic.strip() if topic else None
        base_query = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(~Summary.is_read)
            .order_by(Summary.created_at.asc())
        )

        if user_id is not None:
            base_query = base_query.where(
                (Request.user_id == user_id) | (Request.user_id.is_null(True))
            )
        if chat_id is not None:
            base_query = base_query.where(
                (Request.chat_id == chat_id) | (Request.chat_id.is_null(True))
            )

        fetch_limit: int | None = limit
        if topic_query:
            candidate_limit = max(limit * 5, 25)
            topic_request_ids = self._topic_search.find_request_ids(
                topic_query, candidate_limit=candidate_limit
            )
            if topic_request_ids:
                fetch_limit = len(topic_request_ids)
                base_query = base_query.where(Summary.request.in_(topic_request_ids))
            else:
                fetch_limit = None

        rows_query = base_query
        if fetch_limit is not None:
            rows_query = base_query.limit(fetch_limit)

        rows = rows_query

        results: list[dict[str, Any]] = []
        for row in rows:
            payload = ensure_mapping(row.json_payload)
            request_data = model_to_dict(row.request) or {}

            if topic_query and not self._summary_matches_topic(payload, request_data, topic_query):
                continue

            data = model_to_dict(row) or {}
            req_data = request_data
            req_data.pop("id", None)
            data.update(req_data)
            if "request" in data and "request_id" not in data:
                data["request_id"] = data["request"]
            self._convert_bool_fields(data, ["is_read"])
            results.append(data)
            if len(results) >= limit:
                break
        return results

    async def async_get_unread_summaries(
        self,
        uid: int | None,
        cid: int | None,
        limit: int = 10,
        topic: str | None = None,
    ) -> list[dict[str, Any]]:
        """Async wrapper for :meth:`get_unread_summaries`."""
        return await self._safe_db_operation(
            self.get_unread_summaries,
            user_id=uid,
            chat_id=cid,
            limit=limit,
            topic=topic,
            operation_name="get_unread_summaries",
            read_only=True,
        )

    def get_unread_summary_by_request_id(self, request_id: int) -> dict[str, Any] | None:
        summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where((Summary.request == request_id) & (~Summary.is_read))
            .first()
        )
        if not summary:
            return None
        data = model_to_dict(summary) or {}
        req_data = model_to_dict(summary.request) or {}
        req_data.pop("id", None)
        data.update(req_data)
        if "request" in data and "request_id" not in data:
            data["request_id"] = data["request"]
        self._convert_bool_fields(data, ["is_read"])
        return data

    # ------------------------------------------------------------------
    # Summary embedding CRUD
    # ------------------------------------------------------------------

    def create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Store or update embedding for a summary."""
        try:
            SummaryEmbedding.create(
                summary=summary_id,
                embedding_blob=embedding_blob,
                model_name=model_name,
                model_version=model_version,
                dimensions=dimensions,
                language=language,
            )
        except peewee.IntegrityError:
            SummaryEmbedding.update(
                {
                    SummaryEmbedding.embedding_blob: embedding_blob,
                    SummaryEmbedding.model_name: model_name,
                    SummaryEmbedding.model_version: model_version,
                    SummaryEmbedding.dimensions: dimensions,
                    SummaryEmbedding.language: language,
                    SummaryEmbedding.created_at: dt.datetime.now(UTC),
                }
            ).where(SummaryEmbedding.summary == summary_id).execute()

    async def async_create_or_update_summary_embedding(
        self,
        summary_id: int,
        embedding_blob: bytes,
        model_name: str,
        model_version: str,
        dimensions: int,
        language: str | None = None,
    ) -> None:
        """Asynchronously store or update embedding for a summary."""
        await self._safe_db_operation(
            self.create_or_update_summary_embedding,
            summary_id=summary_id,
            embedding_blob=embedding_blob,
            model_name=model_name,
            model_version=model_version,
            dimensions=dimensions,
            language=language,
            operation_name="create_or_update_summary_embedding",
        )

    def get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Retrieve embedding for a summary."""
        embedding = SummaryEmbedding.get_or_none(SummaryEmbedding.summary == summary_id)
        if embedding is None:
            return None
        return {
            "embedding_blob": embedding.embedding_blob,
            "model_name": embedding.model_name,
            "model_version": embedding.model_version,
            "dimensions": embedding.dimensions,
            "language": embedding.language,
            "created_at": embedding.created_at,
        }

    async def async_get_summary_embedding(self, summary_id: int) -> dict[str, Any] | None:
        """Asynchronously retrieve embedding for a summary."""
        return await self._safe_db_operation(
            self.get_summary_embedding,
            summary_id=summary_id,
            operation_name="get_summary_embedding",
            read_only=True,
        )

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def insert_audit_log(
        self,
        *,
        level: str,
        event: str,
        details_json: JSONValue = None,
    ) -> int:
        entry = AuditLog.create(
            level=level,
            event=event,
            details_json=self._prepare_json_payload(details_json),
        )
        return entry.id

    # ------------------------------------------------------------------
    # Video download delegates
    # ------------------------------------------------------------------

    def create_video_download(self, request_id: int, video_id: str, status: str = "pending") -> int:
        """Create a new video download record."""
        return self._video_downloads.create_video_download(request_id, video_id, status=status)

    def get_video_download_by_request(self, request_id: int):
        """Get video download by request ID."""
        return self._video_downloads.get_video_download_by_request(request_id)

    def get_video_download_by_id(self, download_id: int):
        """Get video download by ID."""
        return self._video_downloads.get_video_download_by_id(download_id)

    def update_video_download_status(
        self,
        download_id: int,
        status: str,
        error_text: str | None = None,
        download_started_at=None,
    ) -> None:
        """Update video download status."""
        self._video_downloads.update_video_download_status(
            download_id,
            status,
            error_text=error_text,
            download_started_at=download_started_at,
        )

    def update_video_download(self, download_id: int, **kwargs) -> None:
        """Update video download with arbitrary fields."""
        self._video_downloads.update_video_download(download_id, **kwargs)
