from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_SQL = r"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  telegram_user_id INTEGER PRIMARY KEY,
  username TEXT,
  is_owner INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chats (
  chat_id INTEGER PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT,
  username TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  correlation_id TEXT,
  chat_id INTEGER,
  user_id INTEGER,
  input_url TEXT,
  normalized_url TEXT,
  dedupe_hash TEXT,
  input_message_id INTEGER,
  fwd_from_chat_id INTEGER,
  fwd_from_msg_id INTEGER,
  lang_detected TEXT,
  content_text TEXT,
  route_version INTEGER DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_dedupe ON requests(dedupe_hash);

CREATE TABLE IF NOT EXISTS telegram_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER UNIQUE,
  message_id INTEGER,
  chat_id INTEGER,
  date_ts INTEGER,
  text_full TEXT,
  entities_json TEXT,
  media_type TEXT,
  media_file_ids_json TEXT,
  forward_from_chat_id INTEGER,
  forward_from_chat_type TEXT,
  forward_from_chat_title TEXT,
  forward_from_message_id INTEGER,
  forward_date_ts INTEGER,
  telegram_raw_json TEXT
);

CREATE TABLE IF NOT EXISTS crawl_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER UNIQUE,
  source_url TEXT,
  endpoint TEXT,
  http_status INTEGER,
  status TEXT,
  options_json TEXT,
  correlation_id TEXT,
  content_markdown TEXT,
  content_html TEXT,
  structured_json TEXT,
  metadata_json TEXT,
  links_json TEXT,
  screenshots_paths_json TEXT,
  raw_response_json TEXT,
  latency_ms INTEGER,
  error_text TEXT
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER,
  provider TEXT,
  model TEXT,
  endpoint TEXT,
  request_headers_json TEXT,
  request_messages_json TEXT,
  response_text TEXT,
  response_json TEXT,
  tokens_prompt INTEGER,
  tokens_completion INTEGER,
  cost_usd REAL,
  latency_ms INTEGER,
  status TEXT,
  error_text TEXT,
  structured_output_used INTEGER,
  structured_output_mode TEXT,
  error_context_json TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER UNIQUE,
  lang TEXT,
  json_payload TEXT,
  insights_json TEXT,
  version INTEGER DEFAULT 1,
  is_read INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  level TEXT NOT NULL,
  event TEXT NOT NULL,
  details_json TEXT
);
"""


@dataclass
class Database:
    path: str
    _logger: logging.Logger = logging.getLogger(__name__)

    def connect(self) -> sqlite3.Connection:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def migrate(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            # Ensure backward-compatible schema updates
            self._ensure_column(conn, "requests", "correlation_id", "TEXT")
            self._ensure_column(conn, "summaries", "insights_json", "TEXT")
            self._ensure_column(conn, "summaries", "is_read", "INTEGER")
            self._ensure_column(conn, "crawl_results", "correlation_id", "TEXT")
            self._ensure_column(conn, "llm_calls", "structured_output_used", "INTEGER")
            self._ensure_column(conn, "llm_calls", "structured_output_mode", "TEXT")
            self._ensure_column(conn, "llm_calls", "error_context_json", "TEXT")
            conn.commit()
        self._logger.info("db_migrated", extra={"path": self.path})

    def _ensure_column(
        self, conn: sqlite3.Connection, table: str, column: str, coltype: str
    ) -> None:
        # Security: Validate table and column names to prevent SQL injection
        if not self._is_valid_identifier(table):
            self._logger.error("invalid_table_name", extra={"table": table})
            return
        if not self._is_valid_identifier(column):
            self._logger.error("invalid_column_name", extra={"column": column})
            return
        if not self._is_valid_column_type(coltype):
            self._logger.error("invalid_column_type", extra={"coltype": coltype})
            return

        # Use parameterized queries where possible, but PRAGMA doesn't support parameters
        # So we validate the identifiers above and use safe string formatting
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

    def _is_valid_identifier(self, identifier: str) -> bool:
        """Validate that an identifier is safe for SQL operations."""
        if not identifier or not isinstance(identifier, str):
            return False
        # Allow only alphanumeric characters and underscores
        return bool(identifier.replace("_", "").isalnum())

    def _is_valid_column_type(self, coltype: str) -> bool:
        """Validate that a column type is safe for SQL operations."""
        if not coltype or not isinstance(coltype, str):
            return False
        # Allow only common SQLite column types
        allowed_types = {
            "INTEGER",
            "TEXT",
            "REAL",
            "BLOB",
            "NUMERIC",
            "INTEGER PRIMARY KEY",
            "TEXT PRIMARY KEY",
        }
        return coltype.upper() in allowed_types

    def execute(self, sql: str, params: Iterable | None = None) -> None:
        with self.connect() as conn:
            conn.execute(sql, tuple(params or ()))
            conn.commit()
        self._logger.debug("db_execute", extra={"sql": sql, "params": list(params or [])[:10]})

    # Fetch helpers
    def fetchone(self, sql: str, params: Iterable | None = None) -> sqlite3.Row | None:
        with self.connect() as conn:
            cur = conn.execute(sql, tuple(params or ()))
            return cur.fetchone()

    def get_database_overview(self) -> dict[str, Any]:
        """Return high-level statistics about the current database state with error tolerance."""
        overview: dict[str, Any] = {
            "path": self.path,
            "path_display": self._mask_path(self.path),
            "errors": [],
            "tables": {},
            "requests_by_status": {},
            "last_request_at": None,
            "last_summary_at": None,
            "last_audit_at": None,
            "tables_truncated": 0,
        }
        errors: list[str] = overview["errors"]

        db_path = Path(self.path)
        try:
            if db_path.exists():
                overview["db_size_bytes"] = db_path.stat().st_size
            else:
                overview["db_size_bytes"] = 0
        except OSError as exc:  # pragma: no cover - filesystem race
            overview["db_size_bytes"] = 0
            errors.append("Could not read database file size")
            self._logger.warning("db_size_stat_failed", extra={"error": str(exc)})

        try:
            with self.connect() as conn:
                tables: dict[str, int] = {}
                try:
                    rows = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                    )
                    table_names = [row[0] for row in rows.fetchall() if isinstance(row[0], str)]
                except sqlite3.Error as exc:  # pragma: no cover - unlikely
                    errors.append("Failed to enumerate tables")
                    self._logger.error("db_tables_list_failed", extra={"error": str(exc)})
                    table_names = []

                max_tables = 25
                for name in table_names[:max_tables]:
                    if not self._is_valid_identifier(name):
                        continue
                    try:
                        safe_table = self._quote_identifier(name)
                        sql = "SELECT COUNT(*) AS cnt FROM " + safe_table  # nosec B608
                        # The table name is validated and quoted via _quote_identifier,
                        # which prevents SQL injection despite the dynamic query string.
                        count_row = conn.execute(sql).fetchone()  # nosec B608
                        tables[name] = int(count_row["cnt"]) if count_row else 0
                    except sqlite3.Error as exc:  # pragma: no cover - corrupted table
                        errors.append(f"Failed to count rows for table '{name}'")
                        self._logger.error(
                            "db_table_count_failed",
                            extra={"table": name, "error": str(exc)},
                        )
                if len(table_names) > max_tables:
                    overview["tables_truncated"] = len(table_names) - max_tables
                overview["tables"] = tables

                if "requests" in tables:
                    try:
                        status_rows = conn.execute(
                            "SELECT status, COUNT(*) AS cnt FROM requests GROUP BY status"
                        ).fetchall()
                        overview["requests_by_status"] = {
                            str(row["status"] or "unknown"): int(row["cnt"]) for row in status_rows
                        }
                    except sqlite3.Error as exc:  # pragma: no cover
                        errors.append("Failed to aggregate request statuses")
                        self._logger.error("db_requests_status_failed", extra={"error": str(exc)})
                    overview["last_request_at"] = self._fetch_single_value(
                        conn,
                        "SELECT created_at FROM requests ORDER BY created_at DESC LIMIT 1",
                    )

                if "summaries" in tables:
                    overview["last_summary_at"] = self._fetch_single_value(
                        conn,
                        "SELECT created_at FROM summaries ORDER BY created_at DESC LIMIT 1",
                    )

                if "audit_logs" in tables:
                    overview["last_audit_at"] = self._fetch_single_value(
                        conn,
                        "SELECT ts FROM audit_logs ORDER BY ts DESC LIMIT 1",
                    )
        except sqlite3.Error as exc:
            errors.append("Failed to query database overview")
            self._logger.error("db_overview_failed", extra={"error": str(exc)})

        tables = overview.get("tables")
        if isinstance(tables, dict):
            overview["total_requests"] = int(tables.get("requests", 0))
            overview["total_summaries"] = int(tables.get("summaries", 0))
        else:
            overview["total_requests"] = 0
            overview["total_summaries"] = 0

        if not errors:
            overview.pop("errors")
        if not overview.get("tables_truncated"):
            overview.pop("tables_truncated", None)
        return overview

    def _fetch_single_value(self, conn: sqlite3.Connection, sql: str) -> Any:
        """Helper to safely fetch a single value, returning None on failure."""
        try:
            row = conn.execute(sql).fetchone()
        except sqlite3.Error as exc:  # pragma: no cover
            self._logger.error("db_fetch_single_failed", extra={"sql": sql, "error": str(exc)})
            return None
        return row[0] if row else None

    def _mask_path(self, path: str) -> str:
        """Return a shortened path representation to avoid leaking full filesystem layout."""
        try:
            p = Path(path)
            name = p.name
            if not name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{name}"
            return name
        except Exception:  # pragma: no cover - defensive
            return "..."

    def get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict | None:
        row = self.fetchone("SELECT * FROM requests WHERE dedupe_hash = ?", (dedupe_hash,))
        return dict(row) if row else None

    def get_request_by_id(self, request_id: int) -> dict | None:
        """Return a request row by its primary key."""
        row = self.fetchone("SELECT * FROM requests WHERE id = ?", (request_id,))
        return dict(row) if row else None

    def get_crawl_result_by_request(self, request_id: int) -> dict | None:
        row = self.fetchone("SELECT * FROM crawl_results WHERE request_id = ?", (request_id,))
        return dict(row) if row else None

    def get_summary_by_request(self, request_id: int) -> dict | None:
        row = self.fetchone("SELECT * FROM summaries WHERE request_id = ?", (request_id,))
        return dict(row) if row else None

    def _quote_identifier(self, identifier: str) -> str:
        """Return a safely quoted SQLite identifier."""
        escaped = identifier.replace('"', '""')
        return '"' + escaped + '"'

    def get_request_by_forward(
        self, fwd_from_chat_id: int | None, fwd_from_msg_id: int | None
    ) -> dict | None:
        """Fetch a cached request for a forwarded message if available."""
        if fwd_from_chat_id is None or fwd_from_msg_id is None:
            return None
        row = self.fetchone(
            "SELECT * FROM requests WHERE fwd_from_chat_id = ? AND fwd_from_msg_id = ? ORDER BY id DESC LIMIT 1",
            (fwd_from_chat_id, fwd_from_msg_id),
        )
        return dict(row) if row else None

    # Convenience insert/update helpers for core flows

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
        sql = (
            "INSERT INTO requests (type, status, correlation_id, chat_id, user_id, input_url, normalized_url, dedupe_hash, "
            "input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected, content_text, route_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(
                sql,
                (
                    type_,
                    status,
                    correlation_id,
                    chat_id,
                    user_id,
                    input_url,
                    normalized_url,
                    dedupe_hash,
                    input_message_id,
                    fwd_from_chat_id,
                    fwd_from_msg_id,
                    lang_detected,
                    content_text,
                    route_version,
                ),
            )
            conn.commit()
            rid = cur.lastrowid
            self._logger.info(
                "request_created",
                extra={"id": rid, "type": type_, "status": status, "cid": correlation_id},
            )
            return rid

    def update_request_status(self, request_id: int, status: str) -> None:
        self.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        self._logger.info("request_status", extra={"id": request_id, "status": status})

    def update_request_correlation_id(self, request_id: int, correlation_id: str) -> None:
        self.execute(
            "UPDATE requests SET correlation_id = ? WHERE id = ?", (correlation_id, request_id)
        )
        self._logger.debug("request_cid", extra={"id": request_id, "cid": correlation_id})

    def update_request_lang_detected(self, request_id: int, lang: str | None) -> None:
        self.execute("UPDATE requests SET lang_detected = ? WHERE id = ?", (lang, request_id))

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
        sql = (
            "INSERT INTO telegram_messages (request_id, message_id, chat_id, date_ts, text_full, entities_json, "
            "media_type, media_file_ids_json, forward_from_chat_id, forward_from_chat_type, forward_from_chat_title, "
            "forward_from_message_id, forward_date_ts, telegram_raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(
                sql,
                (
                    request_id,
                    message_id,
                    chat_id,
                    date_ts,
                    text_full,
                    entities_json,
                    media_type,
                    media_file_ids_json,
                    forward_from_chat_id,
                    forward_from_chat_type,
                    forward_from_chat_title,
                    forward_from_message_id,
                    forward_date_ts,
                    telegram_raw_json,
                ),
            )
            conn.commit()
            mid = cur.lastrowid
            self._logger.debug(
                "telegram_snapshot_inserted", extra={"request_id": request_id, "row_id": mid}
            )
            return mid

    def insert_crawl_result(
        self,
        *,
        request_id: int,
        source_url: str | None,
        endpoint: str | None,
        http_status: int | None,
        status: str,
        options_json: str | None,
        correlation_id: str | None,
        content_markdown: str | None,
        content_html: str | None,
        structured_json: str | None,
        metadata_json: str | None,
        links_json: str | None,
        screenshots_paths_json: str | None,
        raw_response_json: str | None,
        latency_ms: int | None,
        error_text: str | None,
    ) -> int:
        sql = (
            "INSERT INTO crawl_results (request_id, source_url, endpoint, http_status, status, options_json, "
            "correlation_id, content_markdown, content_html, structured_json, metadata_json, links_json, "
            "screenshots_paths_json, raw_response_json, latency_ms, error_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(
                sql,
                (
                    request_id,
                    source_url,
                    endpoint,
                    http_status,
                    status,
                    options_json,
                    correlation_id,
                    content_markdown,
                    content_html,
                    structured_json,
                    metadata_json,
                    links_json,
                    screenshots_paths_json,
                    raw_response_json,
                    latency_ms,
                    error_text,
                ),
            )
            conn.commit()
            cid = cur.lastrowid
            self._logger.debug(
                "crawl_result_inserted",
                extra={"request_id": request_id, "row_id": cid, "status": status},
            )
            return cid

    def insert_llm_call(
        self,
        *,
        request_id: int,
        provider: str,
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
        status: str,
        error_text: str | None,
        structured_output_used: bool | None,
        structured_output_mode: str | None,
        error_context_json: str | None,
    ) -> int:
        sql = (
            "INSERT INTO llm_calls (request_id, provider, model, endpoint, request_headers_json, request_messages_json, "
            "response_text, response_json, tokens_prompt, tokens_completion, cost_usd, latency_ms, status, error_text, "
            "structured_output_used, structured_output_mode, error_context_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(
                sql,
                (
                    request_id,
                    provider,
                    model,
                    endpoint,
                    request_headers_json,
                    request_messages_json,
                    response_text,
                    response_json,
                    tokens_prompt,
                    tokens_completion,
                    cost_usd,
                    latency_ms,
                    status,
                    error_text,
                    int(structured_output_used)
                    if isinstance(structured_output_used, bool)
                    else None,
                    structured_output_mode,
                    error_context_json,
                ),
            )
            conn.commit()
            lid = cur.lastrowid
            self._logger.debug(
                "llm_call_inserted",
                extra={"request_id": request_id, "row_id": lid, "status": status},
            )
            return lid

    def insert_summary(
        self,
        *,
        request_id: int,
        lang: str,
        json_payload: str,
        insights_json: str | None = None,
        version: int = 1,
        is_read: bool = False,
    ) -> int:
        sql = (
            "INSERT INTO summaries (request_id, lang, json_payload, insights_json, version, is_read) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(
                sql, (request_id, lang, json_payload, insights_json, version, int(is_read))
            )
            conn.commit()
            sid = cur.lastrowid
            self._logger.info(
                "summary_inserted",
                extra={"request_id": request_id, "version": version, "is_read": is_read},
            )
            return sid

    def upsert_summary(
        self,
        *,
        request_id: int,
        lang: str,
        json_payload: str,
        insights_json: str | None = None,
        is_read: bool = False,
    ) -> int:
        existing = self.get_summary_by_request(request_id)
        if existing:
            new_version = int(existing.get("version", 1)) + 1
            sql = (
                "UPDATE summaries SET lang = ?, json_payload = ?, insights_json = ?, version = ?, is_read = ?, "
                "created_at = CURRENT_TIMESTAMP WHERE request_id = ?"
            )
            with self.connect() as conn:
                conn.execute(
                    sql, (lang, json_payload, insights_json, new_version, int(is_read), request_id)
                )
                conn.commit()
            self._logger.info(
                "summary_updated",
                extra={"request_id": request_id, "version": new_version, "is_read": is_read},
            )
            return new_version
        else:
            return self.insert_summary(
                request_id=request_id,
                lang=lang,
                json_payload=json_payload,
                insights_json=insights_json,
                version=1,
                is_read=is_read,
            )

    def update_summary_insights(self, request_id: int, insights_json: str | None) -> None:
        sql = "UPDATE summaries SET insights_json = ?, created_at = created_at WHERE request_id = ?"
        with self.connect() as conn:
            conn.execute(sql, (insights_json, request_id))
            conn.commit()
        self._logger.debug(
            "summary_insights_updated",
            extra={"request_id": request_id, "has_insights": bool(insights_json)},
        )

    def get_unread_summaries(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get unread article summaries ordered by creation date."""
        sql = """
            SELECT s.*, r.input_url, r.normalized_url
            FROM summaries s
            JOIN requests r ON s.request_id = r.id
            WHERE s.is_read = 0
            ORDER BY s.created_at DESC
            LIMIT ?
        """
        with self.connect() as conn:
            cur = conn.execute(sql, (limit,))
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def get_unread_summary_by_request_id(self, request_id: int) -> dict | None:
        """Get a specific unread summary by request_id."""
        row = self.fetchone(
            "SELECT s.*, r.input_url, r.normalized_url FROM summaries s JOIN requests r ON s.request_id = r.id WHERE s.request_id = ? AND s.is_read = 0",
            (request_id,),
        )
        return dict(row) if row else None

    def mark_summary_as_read(self, request_id: int) -> None:
        """Mark a summary as read."""
        sql = "UPDATE summaries SET is_read = 1 WHERE request_id = ?"
        with self.connect() as conn:
            conn.execute(sql, (request_id,))
            conn.commit()
        self._logger.debug("summary_marked_read", extra={"request_id": request_id})

    def get_read_status(self, request_id: int) -> bool:
        """Check if a summary has been read."""
        row = self.fetchone("SELECT is_read FROM summaries WHERE request_id = ?", (request_id,))
        return bool(row["is_read"]) if row else False

    def insert_audit_log(self, *, level: str, event: str, details_json: str | None = None) -> int:
        sql = "INSERT INTO audit_logs (level, event, details_json) VALUES (?, ?, ?)"
        with self.connect() as conn:
            cur = conn.execute(sql, (level, event, details_json))
            conn.commit()
            aid = cur.lastrowid
            self._logger.debug("audit_logged", extra={"id": aid, "event": event, "level": level})
            return aid
