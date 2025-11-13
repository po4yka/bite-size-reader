from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import logging
import re
import sqlite3
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import peewee
from peewee import JOIN, fn
from playhouse.sqlite_ext import SqliteExtDatabase

from app.db.models import (
    ALL_MODELS,
    AuditLog,
    Chat,
    CrawlResult,
    LLMCall,
    Request,
    Summary,
    TelegramMessage,
    TopicSearchIndex,
    User,
    UserInteraction,
    database_proxy,
    model_to_dict,
)
from app.services.topic_search_utils import (
    TopicSearchDocument,
    build_topic_search_document,
    ensure_mapping,
    tokenize,
)

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None

# Database operation timeout in seconds
# Prevents indefinite hangs on lock acquisition or slow operations
DB_OPERATION_TIMEOUT = 30.0

# Maximum retries for transient database errors
DB_MAX_RETRIES = 3


class TopicSearchIndexRebuiltError(RuntimeError):
    """Raised to signal that the topic search index was rebuilt mid-operation."""


class RowSqliteDatabase(SqliteExtDatabase):
    """SQLite database subclass that configures the row factory for dict-like access."""

    def _connect(self) -> sqlite3.Connection:
        conn = super()._connect()
        conn.row_factory = sqlite3.Row
        return conn


@dataclass
class Database:
    """Peewee-backed database helper that maintains API parity with the old sqlite3 version."""

    path: str
    _logger: logging.Logger = logging.getLogger(__name__)
    _database: peewee.SqliteDatabase = field(init=False)
    _topic_search_index_reset_in_progress: bool = field(default=False, init=False)
    _topic_search_index_delete_warned: bool = field(default=False, init=False)
    _db_lock: asyncio.Lock = field(init=False)

    def __post_init__(self) -> None:
        if self.path != ":memory":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._database = RowSqliteDatabase(
            self.path,
            pragmas={
                "journal_mode": "wal",
                "synchronous": "normal",
            },
            check_same_thread=False,  # Still needed for asyncio.to_thread() but protected by lock
        )
        database_proxy.initialize(self._database)
        # Initialize lock for thread-safe database access
        # This serializes all database operations to prevent race conditions
        self._db_lock = asyncio.Lock()

    async def _safe_db_operation(
        self,
        operation: Any,
        *args: Any,
        timeout: float = DB_OPERATION_TIMEOUT,
        operation_name: str = "database_operation",
        **kwargs: Any,
    ) -> Any:
        """Execute database operation with timeout and retry protection.

        Args:
            operation: The database operation to execute
            *args: Positional arguments for the operation
            timeout: Timeout in seconds (default: DB_OPERATION_TIMEOUT)
            operation_name: Name for logging purposes
            **kwargs: Keyword arguments for the operation

        Returns:
            Result of the operation

        Raises:
            asyncio.TimeoutError: If operation times out
            peewee.OperationalError: If database is locked or busy after retries
            peewee.IntegrityError: If constraint violation occurs
            Exception: Other database errors
        """
        retries = 0
        last_error = None

        while retries <= DB_MAX_RETRIES:
            try:
                # Acquire lock with timeout to prevent indefinite hangs
                async with asyncio.timeout(timeout):
                    async with self._db_lock:
                        # Execute operation in thread pool
                        result = await asyncio.to_thread(operation, *args, **kwargs)
                        return result

            except asyncio.TimeoutError:
                self._logger.error(
                    "db_operation_timeout",
                    extra={
                        "operation": operation_name,
                        "timeout": timeout,
                        "retries": retries,
                    },
                )
                raise

            except peewee.OperationalError as e:
                # Handle database locked or busy errors
                last_error = e
                error_msg = str(e).lower()

                if "locked" in error_msg or "busy" in error_msg:
                    if retries < DB_MAX_RETRIES:
                        retries += 1
                        wait_time = 0.1 * (2**retries)  # Exponential backoff
                        self._logger.warning(
                            "db_locked_retrying",
                            extra={
                                "operation": operation_name,
                                "retry": retries,
                                "max_retries": DB_MAX_RETRIES,
                                "wait_time": wait_time,
                                "error": str(e),
                            },
                        )
                        await asyncio.sleep(wait_time)
                        continue

                # Non-retryable operational error or max retries exceeded
                self._logger.exception(
                    "db_operational_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                    },
                )
                raise

            except peewee.IntegrityError as e:
                # Constraint violations should not be retried
                self._logger.exception(
                    "db_integrity_error",
                    extra={
                        "operation": operation_name,
                        "error": str(e),
                    },
                )
                raise

            except Exception as e:
                # Unexpected error
                self._logger.exception(
                    "db_unexpected_error",
                    extra={
                        "operation": operation_name,
                        "retries": retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                raise

        # Should not reach here, but handle it anyway
        if last_error:
            raise last_error
        raise RuntimeError(f"Database operation {operation_name} failed after {DB_MAX_RETRIES} retries")

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a context manager yielding the raw sqlite3 connection."""

        with self._database.connection_context():
            yield self._database.connection()

    @staticmethod
    def _normalize_json_container(value: Any) -> Any:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return list(value)
        return value

    @staticmethod
    def _prepare_json_payload(value: Any, *, default: Any | None = None) -> Any | None:
        if value is None:
            value = default
        if value is None:
            return None
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes | bytearray):
            try:
                value = value.decode("utf-8")
            except Exception:
                value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return stripped
        normalized = Database._normalize_json_container(value)
        try:
            json.dumps(normalized)
            return normalized
        except (TypeError, ValueError):
            try:
                coerced = json.loads(json.dumps(normalized, default=str))
            except (TypeError, ValueError):
                return None
            return coerced

    @staticmethod
    def _decode_json_field(value: Any) -> tuple[Any | None, str | None]:
        if value is None:
            return None, None
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes | bytearray):
            try:
                value = value.decode("utf-8")
            except Exception:
                return None, "decode_error"
        if isinstance(value, dict | list):
            return value, None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None, None
            try:
                return json.loads(stripped), None
            except json.JSONDecodeError as exc:
                return None, f"invalid_json:{exc.msg}"
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return None, "unsupported_type"
        return value, None

    @staticmethod
    def _normalize_legacy_json_value(value: Any) -> tuple[Any | None, bool, str | None]:
        if value is None:
            return None, False, None
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes | bytearray):
            try:
                value = value.decode("utf-8")
            except Exception:
                value = value.decode("utf-8", errors="replace")
        if isinstance(value, dict | list):
            return value, False, None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None, True, "blank"
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                return {"__legacy_text__": stripped}, True, "invalid_json"
            return None, False, None
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return {"__legacy_text__": str(value)}, True, "invalid_json"
        return value, False, None

    def migrate(self) -> None:
        with self._database.connection_context():
            with self._database.bind_ctx(ALL_MODELS):
                self._database.create_tables(ALL_MODELS, safe=True)
                self._ensure_schema_compatibility()
        self._run_database_maintenance()
        self._logger.info("db_migrated", extra={"path": self.path})

    def create_backup_copy(self, dest_path: str) -> Path:
        if self.path == ":memory:":
            raise ValueError("Cannot create a backup for an in-memory database")

        source = Path(self.path)
        if not source.exists():
            raise FileNotFoundError(f"Database file not found at {self.path}")

        destination = Path(dest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as conn:
            with sqlite3.connect(str(destination)) as dest_conn:
                conn.backup(dest_conn)
                dest_conn.commit()

        self._logger.info(
            "db_backup_copy_created",
            extra={
                "source": self._mask_path(str(source)),
                "dest": self._mask_path(str(destination)),
            },
        )
        return destination

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        params = tuple(params or ())
        with self._database.connection_context():
            self._database.execute_sql(sql, params)
        self._logger.debug("db_execute", extra={"sql": sql, "params": list(params)[:10]})

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

    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        params = tuple(params or ())
        with self._database.connection_context():
            cursor = self._database.execute_sql(sql, params)
            return cursor.fetchone()

    def get_database_overview(self) -> dict[str, Any]:
        overview: dict[str, Any] = {
            "tables": {},
            "errors": [],
            "tables_truncated": None,
        }

        try:
            with self._database.connection_context():
                tables = {}
                for table in sorted(self._database.get_tables()):
                    try:
                        tables[table] = self._count_table_rows(table)
                    except peewee.DatabaseError as exc:
                        overview["errors"].append(f"Failed to count rows for table '{table}'")
                        self._logger.error(
                            "db_table_count_failed",
                            extra={"table": table, "error": str(exc)},
                        )
                overview["tables"] = tables

                if "requests" in tables:
                    try:
                        status_rows = list(
                            Request.select(Request.status, fn.COUNT(Request.id).alias("cnt"))
                            .group_by(Request.status)
                            .dicts()
                        )
                        overview["requests_by_status"] = {
                            str(row["status"] or "unknown"): int(row["cnt"]) for row in status_rows
                        }
                    except peewee.DatabaseError as exc:
                        overview["errors"].append("Failed to aggregate request statuses")
                        self._logger.error("db_requests_status_failed", extra={"error": str(exc)})

                    overview["last_request_at"] = self._fetch_single_value(
                        "SELECT created_at FROM requests ORDER BY created_at DESC LIMIT 1"
                    )

                if "summaries" in tables:
                    overview["last_summary_at"] = self._fetch_single_value(
                        "SELECT created_at FROM summaries ORDER BY created_at DESC LIMIT 1"
                    )

                if "audit_logs" in tables:
                    overview["last_audit_at"] = self._fetch_single_value(
                        "SELECT ts FROM audit_logs ORDER BY ts DESC LIMIT 1"
                    )
        except peewee.DatabaseError as exc:
            overview["errors"].append("Failed to query database overview")
            self._logger.error("db_overview_failed", extra={"error": str(exc)})

        tables = overview.get("tables")
        if isinstance(tables, dict):
            overview["total_requests"] = int(tables.get("requests", 0))
            overview["total_summaries"] = int(tables.get("summaries", 0))
        else:
            overview["total_requests"] = 0
            overview["total_summaries"] = 0

        if not overview["errors"]:
            overview.pop("errors")
        if not overview.get("tables_truncated"):
            overview.pop("tables_truncated", None)
        return overview

    def _fetch_single_value(self, sql: str) -> Any:
        row = self.fetchone(sql)
        return row[0] if row else None

    def _count_table_rows(self, table_name: str) -> int:
        """Return the number of rows in the given table using Peewee queries."""

        model = next(
            (model for model in ALL_MODELS if model._meta.table_name == table_name),
            None,
        )
        if model is not None:
            return model.select().count()

        dynamic_table = peewee.Table(table_name)
        return dynamic_table.select().count(self._database)

    def _mask_path(self, path: str) -> str:
        try:
            p = Path(path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except Exception:
            return "..."

    @staticmethod
    def _convert_bool_fields(data: dict[str, Any], fields: Iterable[str]) -> None:
        for field_name in fields:
            if field_name in data and data[field_name] is not None:
                data[field_name] = int(bool(data[field_name]))

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        overview = self.get_database_overview()
        required_default = [
            "summary_250",
            "summary_1000",
            "tldr",
            "key_ideas",
            "topic_tags",
            "entities",
            "estimated_reading_time_min",
            "key_stats",
            "answered_questions",
            "readability",
            "seo_keywords",
            "metadata",
            "extractive_quotes",
            "highlights",
            "questions_answered",
            "categories",
            "topic_taxonomy",
            "hallucination_risk",
            "confidence",
            "forwarded_post_extras",
            "key_points_to_remember",
        ]
        required = list(dict.fromkeys(required_fields or required_default))

        posts: dict[str, Any] = {
            "required_fields": required,
            "checked": 0,
            "with_summary": 0,
            "missing_summary": [],
            "missing_fields": [],
            "errors": [],
            "links": {
                "total_links": 0,
                "posts_with_links": 0,
                "missing_data": [],
            },
            "reprocess": [],
        }

        limit_clause = None
        if isinstance(limit, int) and limit > 0:
            limit_clause = limit

        query = (
            Request.select(
                Request.id.alias("request_id"),
                Request.type.alias("request_type"),
                Request.status.alias("request_status"),
                Request.input_url,
                Request.normalized_url,
                Request.fwd_from_chat_id,
                Request.fwd_from_msg_id,
                Summary.json_payload.alias("summary_json"),
                CrawlResult.links_json.alias("links_json"),
                CrawlResult.status.alias("crawl_status"),
            )
            .join(Summary, JOIN.LEFT_OUTER, on=(Summary.request == Request.id))
            .switch(Request)
            .join(CrawlResult, JOIN.LEFT_OUTER, on=(CrawlResult.request == Request.id))
            .order_by(Request.id.desc())
        )

        if limit_clause is not None:
            query = query.limit(limit_clause)

        rows = list(query.dicts())
        posts["checked"] = len(rows)
        posts["links"]["posts_with_links"] = len(rows)

        reprocess_map: dict[int, dict[str, Any]] = {}

        def _coerce_int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        def queue_reprocess(request_id: int, reason: str) -> None:
            if row_type == "forward":
                return
            entry = reprocess_map.get(request_id)
            if entry is None:
                entry = {
                    "request_id": request_id,
                    "type": row_type,
                    "status": row_status,
                    "source": self._describe_request_source(row),
                    "normalized_url": (
                        str(row.get("normalized_url"))
                        if isinstance(row.get("normalized_url"), str) and row.get("normalized_url")
                        else None
                    ),
                    "input_url": (
                        str(row.get("input_url"))
                        if isinstance(row.get("input_url"), str) and row.get("input_url")
                        else None
                    ),
                    "fwd_from_chat_id": _coerce_int(row.get("fwd_from_chat_id")),
                    "fwd_from_msg_id": _coerce_int(row.get("fwd_from_msg_id")),
                    "reasons": set(),
                }
                reprocess_map[request_id] = entry
            entry["reasons"].add(reason)

        for row in rows:
            request_id = int(row["request_id"])
            row_type = str(row.get("request_type") or "unknown")
            row_status = str(row.get("request_status") or "unknown")
            summary_raw = row.get("summary_json")
            links_raw = row.get("links_json")

            summary_payload, summary_error = self._decode_json_field(summary_raw)
            if summary_payload is not None:
                posts["with_summary"] += 1
            else:
                posts["missing_summary"].append(
                    {
                        "request_id": request_id,
                        "status": row.get("request_status"),
                        "request_type": row.get("request_type"),
                        "source": self._describe_request_source(row),
                    }
                )
                queue_reprocess(request_id, "missing_summary")

            missing_fields: list[str] = []
            if summary_error:
                posts["errors"].append(
                    {
                        "request_id": request_id,
                        "error": summary_error,
                    }
                )
                queue_reprocess(request_id, "invalid_summary_json")
                missing_fields = required[:]
            elif summary_payload is not None:
                if isinstance(summary_payload, Mapping):
                    for field in required:
                        value = summary_payload.get(field)
                        if value is None:
                            missing_fields.append(field)
                            continue
                        if isinstance(value, str) and not value.strip():
                            missing_fields.append(field)
                else:
                    missing_fields = required[:]
            if missing_fields:
                if row.get("request_type") != "forward":
                    missing_fields = [
                        field for field in missing_fields if field != "forwarded_post_extras"
                    ]
                if missing_fields:
                    posts["missing_fields"].append(
                        {
                            "request_id": request_id,
                            "missing": missing_fields,
                            "status": row.get("request_status"),
                            "source": self._describe_request_source(row),
                        }
                    )
                    queue_reprocess(request_id, "missing_fields")

            links_count, has_links, links_error = self._count_links_entries(links_raw)
            posts["links"]["total_links"] += links_count
            if not has_links:
                reason = links_error or "absent_links_json"
                posts["links"]["missing_data"].append(
                    {
                        "request_id": request_id,
                        "reason": reason,
                        "status": row.get("request_status"),
                        "source": self._describe_request_source(row),
                    }
                )
                queue_reprocess(request_id, "missing_links")

        if reprocess_map:
            reprocess_entries: list[dict[str, Any]] = []
            for request_id, data in sorted(reprocess_map.items()):
                reasons = data.get("reasons")
                entry = dict(data)
                entry["request_id"] = request_id
                entry["reasons"] = sorted(reasons) if isinstance(reasons, set) else []
                reprocess_entries.append(entry)
            posts["reprocess"] = reprocess_entries

        return {"overview": overview, "posts": posts}

    def _describe_request_source(self, row: Mapping[str, Any]) -> str:
        input_url = row.get("input_url")
        normalized_url = row.get("normalized_url")
        fwd_chat_id = row.get("fwd_from_chat_id")
        fwd_msg_id = row.get("fwd_from_msg_id")
        if input_url:
            return str(input_url)
        if normalized_url:
            return str(normalized_url)
        if fwd_chat_id and fwd_msg_id:
            return f"forward:{fwd_chat_id}:{fwd_msg_id}"
        return "unknown"

    def _count_links_entries(self, links_json: Any) -> tuple[int, bool, str | None]:
        parsed, error = self._decode_json_field(links_json)
        if error:
            return 0, False, error
        if parsed is None:
            return 0, False, None
        if isinstance(parsed, list):
            if not parsed:
                return 1, True, None
            return len(parsed), True, None
        if isinstance(parsed, Mapping):
            if not parsed:
                return 1, True, None
            total = 0
            for value in parsed.values():
                if isinstance(value, list):
                    total += len(value)
                elif value is not None:
                    total += 1
            if total == 0:
                total = 1
            return total, True, None
        return 0, False, "unsupported_links_type"

    def get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
        return model_to_dict(request)

    async def async_get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict[str, Any] | None:
        """Async wrapper for :meth:`get_request_by_dedupe_hash`."""
        return await self._safe_db_operation(
            self.get_request_by_dedupe_hash,
            dedupe_hash,
            operation_name="get_request_by_dedupe_hash",
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
        )

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
        )

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
        if updates and any(field is not None for field in legacy_fields):
            raise ValueError("Cannot mix explicit field arguments with the updates mapping")

        update_values: dict[Any, Any] = {}
        if updates:
            invalid_fields = [
                key
                for key in updates
                if not isinstance(getattr(UserInteraction, key, None), peewee.Field)
            ]
            if invalid_fields:
                raise ValueError(f"Unknown user interaction fields: {', '.join(invalid_fields)}")
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
            except Exception:
                columns = set()
            if updated_at_field.column_name in columns:
                update_values[updated_at_field] = dt.datetime.utcnow()

        UserInteraction.update(update_values).where(UserInteraction.id == interaction_id).execute()

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

    def update_request_status(self, request_id: int, status: str) -> None:
        Request.update({Request.status: status}).where(Request.id == request_id).execute()

    async def async_update_request_status(self, request_id: int, status: str) -> None:
        """Asynchronously update the request status."""
        await self._safe_db_operation(
            self.update_request_status,
            request_id,
            status,
            operation_name="update_request_status",
        )

    def update_request_correlation_id(self, request_id: int, correlation_id: str) -> None:
        Request.update({Request.correlation_id: correlation_id}).where(
            Request.id == request_id
        ).execute()

    def update_request_lang_detected(self, request_id: int, lang: str | None) -> None:
        Request.update({Request.lang_detected: lang}).where(Request.id == request_id).execute()

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
        self._refresh_topic_search_index(request_id)
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
            self._refresh_topic_search_index(request_id)
            return summary.version
        except peewee.IntegrityError:
            update_map: dict[Any, Any] = {
                Summary.lang: lang,
                Summary.json_payload: payload_value,
                Summary.version: Summary.version + 1,
                Summary.created_at: dt.datetime.utcnow(),
            }
            if insights_value is not None:
                update_map[Summary.insights_json] = insights_value
            if is_read is not None:
                update_map[Summary.is_read] = is_read
            query = Summary.update(update_map).where(Summary.request == request_id)
            query.execute()
            updated = Summary.get_or_none(Summary.request == request_id)
            version_val = updated.version if updated else 0
            self._refresh_topic_search_index(request_id)
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

    @staticmethod
    def _yield_topic_fragments(value: Any) -> Iterator[str]:
        """Yield normalized text fragments from arbitrary payload values."""

        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                yield text
            return
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            for item in value:
                yield from Database._yield_topic_fragments(item)
            return
        yield str(value)

    @staticmethod
    def _summary_matches_topic(
        payload: Mapping[str, Any], request_data: Mapping[str, Any], topic: str
    ) -> bool:
        """Return True when a stored summary appears to match the requested topic."""

        terms = [term for term in tokenize(topic) if term]
        if not terms:
            normalized = topic.casefold().strip()
            if not normalized:
                return True
            terms = [normalized]

        metadata = ensure_mapping(payload.get("metadata"))
        candidate_values: list[Any] = [
            payload.get("title"),
            payload.get("summary_250"),
            payload.get("summary_1000"),
            payload.get("tldr"),
            payload.get("topic_tags"),
            payload.get("topic_taxonomy"),
            metadata.get("title"),
            metadata.get("description"),
            metadata.get("keywords"),
            metadata.get("section"),
            metadata.get("topics"),
            metadata.get("category"),
            request_data.get("input_url"),
            request_data.get("normalized_url"),
            request_data.get("content_text"),
        ]

        fragments: list[str] = []
        for value in candidate_values:
            for fragment in Database._yield_topic_fragments(value):
                fragments.append(fragment.casefold())

        if not fragments:
            return False

        combined = " ".join(fragments)
        return all(term in combined for term in terms)

    def get_unread_summaries(
        self, *, limit: int = 10, topic: str | None = None
    ) -> list[dict[str, Any]]:
        """Return unread summary rows optionally filtered by topic text."""

        if limit <= 0:
            return []

        topic_query = topic.strip() if topic else None
        base_query = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(~Summary.is_read)
            .order_by(Summary.created_at.asc())
        )

        fetch_limit: int | None = limit
        if topic_query:
            candidate_limit = max(limit * 5, 25)
            topic_request_ids = self._find_topic_search_request_ids(
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

    @staticmethod
    def _sanitize_fts_term(term: str) -> str:
        sanitized = re.sub(r"[^\w-]+", " ", term)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized

    def _find_topic_search_request_ids(
        self, topic: str, *, candidate_limit: int
    ) -> list[int] | None:
        terms = tokenize(topic)

        if not terms:
            sanitized = self._sanitize_fts_term(topic.casefold())
            if not sanitized:
                return None
            fts_query = f'"{sanitized}"*'
        else:
            sanitized_terms = [self._sanitize_fts_term(term) for term in terms]
            sanitized_terms = [term for term in sanitized_terms if term]
            if not sanitized_terms:
                return None
            phrase = self._sanitize_fts_term(" ".join(terms))
            components: list[str] = []
            wildcard_terms = [f'"{term}"*' for term in sanitized_terms]
            if wildcard_terms:
                components.append(" AND ".join(wildcard_terms))
            if phrase:
                components.append(f'"{phrase}"')
            fts_query = " OR ".join(component for component in components if component)
            if not fts_query:
                return None

        sql = (
            "SELECT rowid FROM topic_search_index "
            "WHERE topic_search_index MATCH ? "
            "ORDER BY bm25(topic_search_index) ASC "
            "LIMIT ?"
        )

        try:
            with self._database.connection_context():
                cursor = self._database.execute_sql(sql, (fts_query, candidate_limit))
                rows = list(cursor)
        except Exception as exc:  # noqa: BLE001 - fallback to scan logic
            self._logger.warning("topic_search_index_lookup_failed", extra={"error": str(exc)})
            return None

        request_ids: list[int] = []
        seen: set[int] = set()
        for row in rows:
            value: Any | None = None
            if isinstance(row, Mapping):
                value = row.get("rowid") or row.get("request_id")
            elif hasattr(row, "keys"):
                try:
                    value = row["rowid"]
                except Exception:
                    try:
                        value = row["request_id"]
                    except Exception:
                        value = None
            if value is None:
                try:
                    value = row[0]
                except Exception:
                    value = None
            if value is None:
                continue
            try:
                request_id = int(value)
            except (TypeError, ValueError):
                continue
            if request_id in seen:
                continue
            request_ids.append(request_id)
            seen.add(request_id)

        return request_ids

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

    def mark_summary_as_read(self, request_id: int) -> None:
        Summary.update({Summary.is_read: True}).where(Summary.request == request_id).execute()

    def get_read_status(self, request_id: int) -> bool:
        summary = Summary.get_or_none(Summary.request == request_id)
        return bool(summary.is_read) if summary else False

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

    # -- internal helpers -------------------------------------------------

    def _ensure_schema_compatibility(self) -> None:
        checks = [
            ("requests", "correlation_id", "TEXT"),
            ("summaries", "insights_json", "TEXT"),
            ("summaries", "is_read", "INTEGER"),
            ("crawl_results", "correlation_id", "TEXT"),
            ("crawl_results", "firecrawl_success", "INTEGER"),
            ("crawl_results", "firecrawl_error_code", "TEXT"),
            ("crawl_results", "firecrawl_error_message", "TEXT"),
            ("crawl_results", "firecrawl_details_json", "TEXT"),
            ("llm_calls", "structured_output_used", "INTEGER"),
            ("llm_calls", "structured_output_mode", "TEXT"),
            ("llm_calls", "error_context_json", "TEXT"),
            ("llm_calls", "openrouter_response_text", "TEXT"),
            ("llm_calls", "openrouter_response_json", "TEXT"),
            ("user_interactions", "updated_at", "DATETIME"),
        ]
        for table, column, coltype in checks:
            self._ensure_column(table, column, coltype)
        self._migrate_openrouter_response_payloads()
        self._migrate_firecrawl_raw_payload()
        self._coerce_json_columns()
        self._ensure_topic_search_index()

    def _ensure_column(self, table: str, column: str, coltype: str) -> None:
        if table not in self._database.get_tables():
            return
        existing = {col.name for col in self._database.get_columns(table)}
        if column in existing:
            return
        self._database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    def _coerce_json_columns(self) -> None:
        columns_map: dict[str, tuple[str, ...]] = {
            "telegram_messages": (
                "entities_json",
                "media_file_ids_json",
                "telegram_raw_json",
            ),
            "crawl_results": (
                "options_json",
                "structured_json",
                "metadata_json",
                "links_json",
                "screenshots_paths_json",
                "firecrawl_details_json",
                "raw_response_json",
            ),
            "llm_calls": (
                "request_headers_json",
                "request_messages_json",
                "response_json",
                "openrouter_response_json",
                "error_context_json",
            ),
            "summaries": ("json_payload", "insights_json"),
            "audit_logs": ("details_json",),
        }
        tables = set(self._database.get_tables())
        for table, columns in columns_map.items():
            if table not in tables:
                continue
            for column in columns:
                self._coerce_json_column(table, column)

    def _ensure_topic_search_index(self) -> None:
        table_name = TopicSearchIndex._meta.table_name
        with self._database.connection_context():
            tables = set(self._database.get_tables())
            if table_name not in tables:
                TopicSearchIndex.create_table()
                self._rebuild_topic_search_index()
                return
            try:
                summary_count = Summary.select().where(Summary.json_payload.is_null(False)).count()
                index_count = TopicSearchIndex.select().count()
            except peewee.DatabaseError as exc:  # pragma: no cover - defensive path
                self._logger.warning("topic_search_index_count_failed", extra={"error": str(exc)})
                summary_count = -1
                index_count = -2

            if summary_count < 0 or index_count != summary_count:
                try:
                    self._rebuild_topic_search_index()
                except TopicSearchIndexRebuiltError:
                    return

    def _refresh_topic_search_index(self, request_id: int) -> None:
        try:
            with self._database.connection_context():
                summary = (
                    Summary.select(Summary, Request)
                    .join(Request)
                    .where((Summary.request == request_id) & (Summary.json_payload.is_null(False)))
                    .first()
                )
                if not summary:
                    self._remove_topic_search_index_entry(request_id)
                    return

                payload = ensure_mapping(summary.json_payload)
                if not payload:
                    self._remove_topic_search_index_entry(request_id)
                    return

                request_data = {
                    "normalized_url": getattr(summary.request, "normalized_url", None),
                    "input_url": getattr(summary.request, "input_url", None),
                    "content_text": getattr(summary.request, "content_text", None),
                }
                document = build_topic_search_document(
                    request_id=request_id,
                    payload=payload,
                    request_data=request_data,
                )
                if not document:
                    self._remove_topic_search_index_entry(request_id)
                    return

                try:
                    self._write_topic_search_index(document)
                except TopicSearchIndexRebuiltError:
                    return
        except Exception as exc:  # noqa: BLE001 - logging and continue
            self._logger.warning(
                "topic_search_index_refresh_failed",
                extra={"request_id": request_id, "error": str(exc)},
            )

    def _write_topic_search_index(self, document: TopicSearchDocument) -> None:
        self._delete_topic_search_index_row(document.request_id)
        self._database.execute_sql(
            """
            INSERT INTO topic_search_index(
                rowid, request_id, url, title, snippet, source, published_at, body, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.request_id,
                str(document.request_id),
                document.url or "",
                document.title or "",
                document.snippet or "",
                document.source or "",
                document.published_at or "",
                document.body,
                document.tags_text or "",
            ),
        )

    def _remove_topic_search_index_entry(self, request_id: int) -> None:
        self._delete_topic_search_index_row(request_id)

    def _rebuild_topic_search_index(self) -> None:
        with self._database.connection_context():
            self._clear_topic_search_index()
            rows = (
                Summary.select(Summary, Request)
                .join(Request)
                .where(Summary.json_payload.is_null(False))
            )
            rebuilt = 0
            try:
                for row in rows.iterator():
                    payload = ensure_mapping(row.json_payload)
                    if not payload:
                        continue
                    request_data = {
                        "normalized_url": getattr(row.request, "normalized_url", None),
                        "input_url": getattr(row.request, "input_url", None),
                        "content_text": getattr(row.request, "content_text", None),
                    }
                    document = build_topic_search_document(
                        request_id=row.request.id,
                        payload=payload,
                        request_data=request_data,
                    )
                    if not document:
                        continue
                    self._write_topic_search_index(document)
                    rebuilt += 1
            except TopicSearchIndexRebuiltError:
                return
        if rebuilt:
            self._logger.info("topic_search_index_rebuilt", extra={"rows": rebuilt})

    def _clear_topic_search_index(self) -> None:
        """Remove all rows from the topic search FTS index."""

        self._database.execute_sql(
            "INSERT INTO topic_search_index(topic_search_index) VALUES ('delete-all')"
        )

    def _delete_topic_search_index_row(self, rowid: int) -> None:
        """Remove a single row from the topic search FTS index."""

        try:
            self._database.execute_sql(
                "DELETE FROM topic_search_index WHERE rowid = ?",
                (rowid,),
            )
        except peewee.DatabaseError as exc:
            message = str(exc)
            if "malformed" in message.lower():
                self._handle_topic_search_index_error(exc, rowid)
                return

            self._log_topic_search_delete_fallback(rowid, message)

    def _log_topic_search_delete_fallback(self, rowid: int, message: str) -> None:
        """Log degraded delete path, but only warn once to avoid noise."""

        log_extra = {"rowid": rowid, "error": message}
        if not self._topic_search_index_delete_warned:
            self._topic_search_index_delete_warned = True
            self._logger.warning("topic_search_index_delete_failed_primary", extra=log_extra)
        else:  # pragma: no cover - logging noise suppression
            self._logger.debug("topic_search_index_delete_failed_primary", extra=log_extra)

    def _handle_topic_search_index_error(self, exc: peewee.DatabaseError, rowid: int) -> None:
        """Handle unrecoverable FTS errors by rebuilding the index."""

        message = str(exc)
        self._logger.error(
            "topic_search_index_delete_failed",
            extra={"rowid": rowid, "error": message},
        )
        if "malformed" not in message.lower():
            raise exc

        self._reset_topic_search_index()
        raise TopicSearchIndexRebuiltError from exc

    def _reset_topic_search_index(self) -> None:
        """Drop and rebuild the topic search index to recover from corruption."""

        if self._topic_search_index_reset_in_progress:
            return

        self._topic_search_index_reset_in_progress = True
        try:
            self._logger.warning("topic_search_index_resetting_due_to_error")
            with self._database.connection_context():
                try:
                    TopicSearchIndex.drop_table(safe=True)
                except peewee.DatabaseError:
                    pass
                TopicSearchIndex.create_table()
            try:
                self._rebuild_topic_search_index()
            except TopicSearchIndexRebuiltError:
                return
        except peewee.DatabaseError as reset_exc:  # pragma: no cover - defensive
            self._logger.exception(
                "topic_search_index_reset_failed",
                extra={"error": str(reset_exc)},
            )
        finally:
            self._topic_search_index_reset_in_progress = False

    def _coerce_json_column(self, table: str, column: str) -> None:
        model = next((m for m in ALL_MODELS if m._meta.table_name == table), None)
        if model is None:
            return
        field = getattr(model, column)

        # Wrap the entire migration in a transaction for atomicity
        with self._database.atomic():
            query = model.select(model.id, field).where(field.is_null(False)).tuples()
            updates = 0
            wrapped = 0
            blanks = 0

            try:
                for row_id, raw_value in query:
                    normalized, should_update, reason = self._normalize_legacy_json_value(raw_value)
                    if not should_update:
                        continue
                    if reason == "invalid_json" and isinstance(raw_value, str):
                        wrapped += 1
                    if reason == "blank":
                        blanks += 1
                    model.update({field: normalized}).where(model.id == row_id).execute()
                    updates += 1
            except Exception as exc:
                self._logger.error(
                    "json_column_coercion_failed",
                    extra={
                        "table": table,
                        "column": column,
                        "error": str(exc),
                        "rows_processed": updates,
                    },
                )
                # Transaction will be rolled back automatically
                raise

        if updates:
            extra: dict[str, Any] = {"table": table, "column": column, "rows": updates}
            if wrapped:
                extra["wrapped"] = wrapped
            if blanks:
                extra["blanks"] = blanks
            self._logger.info("json_column_coerced", extra=extra)

    def _migrate_firecrawl_raw_payload(self) -> None:
        rows = (
            CrawlResult.select()
            .where(
                (CrawlResult.raw_response_json.is_null(False))
                & (fn.trim(CrawlResult.raw_response_json) != "")
            )
            .iterator()
        )
        updated = 0
        for row in rows:
            raw_value = row.raw_response_json
            if not raw_value:
                continue
            if isinstance(raw_value, dict | list):
                payload = raw_value
            else:
                try:
                    payload = json.loads(raw_value)
                except Exception as exc:
                    self._logger.debug(
                        "firecrawl_migration_json_error",
                        extra={"error": str(exc), "row_id": row.id},
                    )
                    continue
            if not isinstance(payload, Mapping):
                continue

            success_val = payload.get("success")
            success_bool: bool | None
            if isinstance(success_val, bool):
                success_bool = success_val
            elif isinstance(success_val, int | float):
                success_bool = bool(success_val)
            else:
                success_bool = None

            error_code = payload.get("code")
            if error_code is not None and not isinstance(error_code, str):
                error_code = str(error_code)

            error_message = payload.get("error")
            if error_message is not None and not isinstance(error_message, str):
                error_message = str(error_message)

            details = payload.get("details")
            details_json = self._prepare_json_payload(details)

            CrawlResult.update(
                {
                    CrawlResult.firecrawl_success: success_bool,
                    CrawlResult.firecrawl_error_code: error_code,
                    CrawlResult.firecrawl_error_message: error_message,
                    CrawlResult.firecrawl_details_json: details_json,
                    CrawlResult.raw_response_json: None,
                }
            ).where(CrawlResult.id == row.id).execute()
            updated += 1

        if updated:
            self._logger.info("firecrawl_payload_migrated", extra={"rows": updated})

    def _migrate_openrouter_response_payloads(self) -> None:
        rows = (
            LLMCall.select()
            .where(
                (LLMCall.provider == "openrouter")
                & (
                    (LLMCall.response_text.is_null(False) & (fn.trim(LLMCall.response_text) != ""))
                    | (
                        LLMCall.response_json.is_null(False)
                        & (fn.trim(LLMCall.response_json) != "")
                    )
                )
            )
            .iterator()
        )
        updated = 0
        for row in rows:
            LLMCall.update(
                {
                    LLMCall.openrouter_response_text: peewee.fn.COALESCE(
                        LLMCall.openrouter_response_text, row.response_text
                    ),
                    LLMCall.openrouter_response_json: peewee.fn.COALESCE(
                        LLMCall.openrouter_response_json, row.response_json
                    ),
                    LLMCall.response_text: None,
                    LLMCall.response_json: None,
                }
            ).where(LLMCall.id == row.id).execute()
            updated += 1

        if updated:
            self._logger.info("openrouter_payload_migrated", extra={"rows": updated})

    def _run_database_maintenance(self) -> None:
        if self.path == ":memory":
            self._logger.debug("db_maintenance_skipped_in_memory")
            return
        self._run_analyze()
        self._run_vacuum()

    def _run_analyze(self) -> None:
        try:
            with self._database.connection_context():
                self._database.execute_sql("ANALYZE;")
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_analyze_failed",
                extra={"path": self._mask_path(self.path), "error": str(exc)},
            )

    def _run_vacuum(self) -> None:
        try:
            with self._database.connection_context():
                self._database.execute_sql("VACUUM;")
        except peewee.DatabaseError as exc:
            self._logger.warning(
                "db_vacuum_failed",
                extra={"path": self._mask_path(self.path), "error": str(exc)},
            )
