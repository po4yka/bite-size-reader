"""Schema migration helpers for DatabaseSessionManager."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.db.models import ALL_MODELS

if TYPE_CHECKING:
    import logging

    import peewee


class SchemaMigrator:
    """Encapsulate schema compatibility and JSON coercion logic."""

    def __init__(self, database: peewee.SqliteDatabase, logger: logging.Logger) -> None:
        self._database = database
        self._logger = logger

    def ensure_schema_compatibility(self) -> None:
        """Execute schema migrations for backward compatibility."""
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
            ("summary_embeddings", "language", "TEXT"),  # Multi-language support
            ("collections", "parent_id", "INTEGER"),
            ("collections", "position", "INTEGER"),
            ("collections", "is_shared", "INTEGER"),
            ("collections", "share_count", "INTEGER"),
            ("collections", "is_deleted", "INTEGER"),
            ("collections", "deleted_at", "DATETIME"),
            ("collection_items", "position", "INTEGER"),
        ]
        for table, column, coltype in checks:
            self._ensure_column(table, column, coltype)

        self._coerce_json_columns()

    def _ensure_column(self, table: str, column: str, coltype: str) -> None:
        if table not in self._database.get_tables():
            return
        existing = {col.name for col in self._database.get_columns(table)}
        if column not in existing:
            self._database.execute_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    def _coerce_json_columns(self) -> None:
        """Ensure JSON columns contain valid JSON data."""
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

    @staticmethod
    def _normalize_legacy_json_value(value: Any) -> tuple[Any | None, bool, str | None]:
        if value is None:
            return None, False, None
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytes | bytearray):
            try:
                value = value.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
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

    def _coerce_json_column(self, table: str, column: str) -> None:
        model = next((m for m in ALL_MODELS if m._meta.table_name == table), None)
        if model is None:
            return
        field = getattr(model, column)

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
                self._logger.exception(
                    "json_column_coercion_failed",
                    extra={
                        "table": table,
                        "column": column,
                        "error": str(exc),
                        "rows_processed": updates,
                    },
                )
                raise

        if updates:
            extra: dict[str, Any] = {"table": table, "column": column, "rows": updates}
            if wrapped:
                extra["wrapped"] = wrapped
            if blanks:
                extra["blanks"] = blanks
            self._logger.info("json_column_coerced", extra=extra)
