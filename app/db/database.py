from __future__ import annotations

import contextlib
import datetime as dt
import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import peewee
from peewee import JOIN, fn

from app.db.models import (
    ALL_MODELS,
    AuditLog,
    Chat,
    CrawlResult,
    LLMCall,
    Request,
    Summary,
    TelegramMessage,
    User,
    UserInteraction,
    database_proxy,
    model_to_dict,
)


class RowSqliteDatabase(peewee.SqliteDatabase):
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

    def __post_init__(self) -> None:
        if self.path != ":memory":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._database = RowSqliteDatabase(
            self.path,
            pragmas={
                "journal_mode": "wal",
                "synchronous": "normal",
            },
            check_same_thread=False,
        )
        database_proxy.initialize(self._database)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Return a context manager yielding the raw sqlite3 connection."""

        with self._database.connection_context():
            yield self._database.connection()

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
            summary_json = row.get("summary_json")
            links_json = row.get("links_json")

            if summary_json:
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
            if summary_json:
                try:
                    payload = json.loads(summary_json)
                except json.JSONDecodeError as exc:
                    posts["errors"].append(
                        {
                            "request_id": request_id,
                            "error": f"invalid_json:{exc}",
                        }
                    )
                    queue_reprocess(request_id, "invalid_summary_json")
                    payload = {}
                if isinstance(payload, Mapping):
                    for field in required:
                        value = payload.get(field)
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

            links_count, has_links, links_error = self._count_links_entries(links_json)
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

    def _count_links_entries(self, links_json: str | None) -> tuple[int, bool, str | None]:
        if not links_json:
            return 0, False, None
        try:
            data = json.loads(links_json)
        except json.JSONDecodeError as exc:
            return 0, False, f"invalid_json:{exc.msg}"
        if isinstance(data, list):
            if not data:
                return 1, True, None
            return len(data), True, None
        if isinstance(data, Mapping):
            if not data:
                return 1, True, None
            total = 0
            for value in data.values():
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

    def get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        request = Request.get_or_none(Request.id == request_id)
        return model_to_dict(request)

    def get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        result = CrawlResult.get_or_none(CrawlResult.request == request_id)
        data = model_to_dict(result)
        if data:
            self._convert_bool_fields(data, ["firecrawl_success"])
        return data

    def get_summary_by_request(self, request_id: int) -> dict[str, Any] | None:
        summary = Summary.get_or_none(Summary.request == request_id)
        data = model_to_dict(summary)
        if data:
            self._convert_bool_fields(data, ["is_read"])
        return data

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
        update_values: dict[Any, Any] = {UserInteraction.updated_at: dt.datetime.utcnow()}
        if updates:
            for key, value in updates.items():
                field_obj = getattr(UserInteraction, key, None)
                if isinstance(field_obj, peewee.Field):
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

        if len(update_values) == 1:
            return

        UserInteraction.update(update_values).where(UserInteraction.id == interaction_id).execute()

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
        entities_json: str | None,
        media_type: str | None,
        media_file_ids_json: str | None,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: str | None,
    ) -> int:
        try:
            message = TelegramMessage.create(
                request=request_id,
                message_id=message_id,
                chat_id=chat_id,
                date_ts=date_ts,
                text_full=text_full,
                entities_json=entities_json,
                media_type=media_type,
                media_file_ids_json=media_file_ids_json,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_type=forward_from_chat_type,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                forward_date_ts=forward_date_ts,
                telegram_raw_json=telegram_raw_json,
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
        options_json: str | None,
        correlation_id: str | None,
        content_markdown: str | None,
        content_html: str | None,
        structured_json: str | None,
        metadata_json: str | None,
        links_json: str | None,
        screenshots_paths_json: str | None,
        firecrawl_success: bool | None,
        firecrawl_error_code: str | None,
        firecrawl_error_message: str | None,
        firecrawl_details_json: str | None,
        raw_response_json: str | None,
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
                options_json=options_json,
                correlation_id=correlation_id,
                content_markdown=content_markdown,
                content_html=content_html,
                structured_json=structured_json,
                metadata_json=metadata_json,
                links_json=links_json,
                screenshots_paths_json=screenshots_paths_json,
                firecrawl_success=firecrawl_success,
                firecrawl_error_code=firecrawl_error_code,
                firecrawl_error_message=firecrawl_error_message,
                firecrawl_details_json=firecrawl_details_json,
                raw_response_json=raw_response_json,
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
        request_headers_json: str | None,
        request_messages_json: str | None,
        response_text: str | None,
        response_json: str | None,
        tokens_prompt: int | None,
        tokens_completion: int | None,
        cost_usd: float | None,
        latency_ms: int | None,
        status: str | None,
        error_text: str | None,
        structured_output_used: bool | None,
        structured_output_mode: str | None,
        error_context_json: str | None,
    ) -> int:
        payload: dict[Any, Any] = {
            LLMCall.request: request_id,
            LLMCall.provider: provider,
            LLMCall.model: model,
            LLMCall.endpoint: endpoint,
            LLMCall.request_headers_json: request_headers_json,
            LLMCall.request_messages_json: request_messages_json,
            LLMCall.tokens_prompt: tokens_prompt,
            LLMCall.tokens_completion: tokens_completion,
            LLMCall.cost_usd: cost_usd,
            LLMCall.latency_ms: latency_ms,
            LLMCall.status: status,
            LLMCall.error_text: error_text,
            LLMCall.structured_output_used: structured_output_used,
            LLMCall.structured_output_mode: structured_output_mode,
            LLMCall.error_context_json: error_context_json,
        }
        if provider == "openrouter":
            payload[LLMCall.openrouter_response_text] = response_text
            payload[LLMCall.openrouter_response_json] = response_json
            payload[LLMCall.response_text] = None
            payload[LLMCall.response_json] = None
        else:
            payload[LLMCall.response_text] = response_text
            payload[LLMCall.response_json] = response_json

        call = LLMCall.create(**{field.name: value for field, value in payload.items()})
        return call.id

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
        json_payload: str | None,
        insights_json: str | None = None,
        version: int = 1,
        is_read: bool = False,
    ) -> int:
        summary = Summary.create(
            request=request_id,
            lang=lang,
            json_payload=json_payload,
            insights_json=insights_json,
            version=version,
            is_read=is_read,
        )
        return summary.id

    def upsert_summary(
        self,
        *,
        request_id: int,
        lang: str | None,
        json_payload: str | None,
        insights_json: str | None = None,
        is_read: bool | None = None,
    ) -> int:
        try:
            summary = Summary.create(
                request=request_id,
                lang=lang,
                json_payload=json_payload,
                insights_json=insights_json,
                version=1,
                is_read=is_read if is_read is not None else False,
            )
            return summary.version
        except peewee.IntegrityError:
            update_map: dict[Any, Any] = {
                Summary.lang: lang,
                Summary.json_payload: json_payload,
                Summary.version: Summary.version + 1,
                Summary.created_at: dt.datetime.utcnow(),
            }
            if insights_json is not None:
                update_map[Summary.insights_json] = insights_json
            if is_read is not None:
                update_map[Summary.is_read] = is_read
            query = Summary.update(update_map).where(Summary.request == request_id)
            query.execute()
            updated = Summary.get_or_none(Summary.request == request_id)
            return updated.version if updated else 0

    def update_summary_insights(self, request_id: int, insights_json: str | None) -> None:
        Summary.update({Summary.insights_json: insights_json}).where(
            Summary.request == request_id
        ).execute()

    def get_unread_summaries(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = (
            Summary.select(Summary, Request)
            .join(Request)
            .where(~Summary.is_read)
            .order_by(Summary.created_at.asc())
            .limit(limit)
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            data = model_to_dict(row) or {}
            req_data = model_to_dict(row.request) or {}
            req_data.pop("id", None)
            data.update(req_data)
            if "request" in data and "request_id" not in data:
                data["request_id"] = data["request"]
            self._convert_bool_fields(data, ["is_read"])
            results.append(data)
        return results

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
        details_json: str | None = None,
    ) -> int:
        entry = AuditLog.create(level=level, event=event, details_json=details_json)
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
        ]
        for table, column, coltype in checks:
            self._ensure_column(table, column, coltype)
        self._migrate_openrouter_response_payloads()
        self._migrate_firecrawl_raw_payload()

    def _ensure_column(self, table: str, column: str, coltype: str) -> None:
        if table not in self._database.get_tables():
            return
        existing = {col.name for col in self._database.get_columns(table)}
        if column in existing:
            return
        self._database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

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
            raw_text = row.raw_response_json
            if not raw_text:
                continue
            try:
                payload = json.loads(raw_text)
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

            details_json = None
            details = payload.get("details")
            if details is not None:
                try:
                    details_json = json.dumps(details)
                except Exception:
                    details_json = None

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
