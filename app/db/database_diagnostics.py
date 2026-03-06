"""Diagnostics helpers for Database."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import peewee
from peewee import JOIN, fn

from app.db.json_utils import decode_json_field
from app.db.models import ALL_MODELS, CrawlResult, Request, Summary

if TYPE_CHECKING:
    import logging


class DatabaseDiagnostics:
    """Encapsulate database diagnostics and integrity checks."""

    def __init__(
        self,
        database: peewee.SqliteDatabase,
        logger: logging.Logger,
    ) -> None:
        self._database = database
        self._logger = logger

    def get_database_overview(self) -> dict[str, Any]:
        overview: dict[str, Any] = {
            "tables": {},
            "errors": [],
            "tables_truncated": None,
        }

        try:
            with self._database.connection_context():
                table_counts: dict[str, int] = {}
                table_names: set[str] = set()
                for table in sorted(self._database.get_tables()):
                    table_names.add(table)
                    try:
                        table_counts[table] = self._count_table_rows(table)
                    except peewee.DatabaseError as exc:
                        overview["errors"].append(f"Failed to count rows for table '{table}'")
                        self._logger.exception(
                            "db_table_count_failed",
                            extra={"table": table, "error": str(exc)},
                        )
                overview["tables"] = table_counts

                if "requests" in table_names:
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
                        self._logger.exception(
                            "db_requests_status_failed", extra={"error": str(exc)}
                        )

                    overview["last_request_at"] = self._fetch_single_value(
                        "SELECT created_at FROM requests ORDER BY created_at DESC LIMIT 1"
                    )

                if "summaries" in table_names:
                    overview["last_summary_at"] = self._fetch_single_value(
                        "SELECT created_at FROM summaries ORDER BY created_at DESC LIMIT 1"
                    )

                if "audit_logs" in table_names:
                    overview["last_audit_at"] = self._fetch_single_value(
                        "SELECT ts FROM audit_logs ORDER BY ts DESC LIMIT 1"
                    )
        except peewee.DatabaseError as exc:
            overview["errors"].append("Failed to query database overview")
            self._logger.exception("db_overview_failed", extra={"error": str(exc)})

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

    def verify_processing_integrity(
        self,
        *,
        required_fields: Iterable[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        overview = self.get_database_overview()
        required_default = self._required_integrity_fields()
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

        query = self._integrity_query()

        if limit_clause is not None:
            query = query.limit(limit_clause)

        total_rows = query.count()
        posts["checked"] = total_rows
        posts["links"]["posts_with_links"] = total_rows

        reprocess_map: dict[int, dict[str, Any]] = {}
        for row in query.dicts():
            self._process_integrity_row(
                row=row,
                required=required,
                posts=posts,
                reprocess_map=reprocess_map,
            )

        posts["reprocess"] = self._build_reprocess_entries(reprocess_map)

        return {"overview": overview, "posts": posts}

    @staticmethod
    def _required_integrity_fields() -> list[str]:
        return [
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

    @staticmethod
    def _integrity_query() -> Any:
        return (
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

    def _process_integrity_row(
        self,
        *,
        row: Mapping[str, Any],
        required: list[str],
        posts: dict[str, Any],
        reprocess_map: dict[int, dict[str, Any]],
    ) -> None:
        request_id = int(row["request_id"])
        row_type = str(row.get("request_type") or "unknown")

        summary_payload, summary_error = decode_json_field(row.get("summary_json"))
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
            self._queue_reprocess(reprocess_map, row, row_type, request_id, "missing_summary")
        if summary_error:
            self._queue_reprocess(reprocess_map, row, row_type, request_id, "invalid_summary_json")

        missing_fields = self._collect_missing_fields(
            row=row,
            required=required,
            summary_payload=summary_payload,
            summary_error=summary_error,
            posts=posts,
        )
        if missing_fields:
            posts["missing_fields"].append(
                {
                    "request_id": request_id,
                    "missing": missing_fields,
                    "status": row.get("request_status"),
                    "source": self._describe_request_source(row),
                }
            )
            self._queue_reprocess(reprocess_map, row, row_type, request_id, "missing_fields")

        links_count, has_links, links_error = self._count_links_entries(row.get("links_json"))
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
            self._queue_reprocess(reprocess_map, row, row_type, request_id, "missing_links")

    def _collect_missing_fields(
        self,
        *,
        row: Mapping[str, Any],
        required: list[str],
        summary_payload: Any,
        summary_error: str | None,
        posts: dict[str, Any],
    ) -> list[str]:
        request_id = int(row["request_id"])
        missing_fields: list[str] = []
        if summary_error:
            posts["errors"].append({"request_id": request_id, "error": summary_error})
            missing_fields = required[:]
        elif summary_payload is not None:
            if isinstance(summary_payload, Mapping):
                for field in required:
                    value = summary_payload.get(field)
                    if value is None or (isinstance(value, str) and not value.strip()):
                        missing_fields.append(field)
            else:
                missing_fields = required[:]

        if row.get("request_type") != "forward":
            missing_fields = [field for field in missing_fields if field != "forwarded_post_extras"]
        return missing_fields

    def _queue_reprocess(
        self,
        reprocess_map: dict[int, dict[str, Any]],
        row: Mapping[str, Any],
        row_type: str,
        request_id: int,
        reason: str,
    ) -> None:
        if row_type == "forward":
            return
        entry = reprocess_map.get(request_id)
        if entry is None:
            entry = {
                "request_id": request_id,
                "type": row_type,
                "status": str(row.get("request_status") or "unknown"),
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
                "fwd_from_chat_id": self._coerce_int(row.get("fwd_from_chat_id")),
                "fwd_from_msg_id": self._coerce_int(row.get("fwd_from_msg_id")),
                "reasons": set(),
            }
            reprocess_map[request_id] = entry
        entry["reasons"].add(reason)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _build_reprocess_entries(reprocess_map: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for request_id, data in sorted(reprocess_map.items()):
            reasons = data.get("reasons")
            entry = dict(data)
            entry["request_id"] = request_id
            entry["reasons"] = sorted(reasons) if isinstance(reasons, set) else []
            entries.append(entry)
        return entries

    def _fetch_single_value(self, sql: str) -> Any:
        params: tuple[Any, ...] = ()
        with self._database.connection_context():
            cursor = self._database.execute_sql(sql, params)
            row = cursor.fetchone()
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

    @staticmethod
    def _describe_request_source(row: Mapping[str, Any]) -> str:
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
        parsed, error = decode_json_field(links_json)
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
