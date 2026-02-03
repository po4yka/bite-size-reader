"""Schema migration helpers for DatabaseSessionManager.

Column additions are now handled by versioned migration files in
``app/cli/migrations/`` (see 005_add_schema_columns.py).  This module
retains only the idempotent JSON coercion logic that must run on every
startup to fix malformed data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.db.json_utils import normalize_legacy_json_value
from app.db.models import ALL_MODELS

if TYPE_CHECKING:
    import logging

    import peewee


class SchemaMigrator:
    """Idempotent JSON coercion for database columns.

    Column additions that previously lived here have been moved to
    ``app/cli/migrations/005_add_schema_columns.py``.
    """

    def __init__(self, database: peewee.SqliteDatabase, logger: logging.Logger) -> None:
        self._database = database
        self._logger = logger

    def ensure_schema_compatibility(self) -> None:
        """Run idempotent JSON coercion on startup.

        Column additions are no longer performed here -- they are handled by
        the versioned migration runner (see ``005_add_schema_columns.py``).
        """
        self._coerce_json_columns()

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
                    normalized, should_update, reason = normalize_legacy_json_value(raw_value)
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
