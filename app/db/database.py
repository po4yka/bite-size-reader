from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import logging


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
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER UNIQUE,
  lang TEXT,
  json_payload TEXT,
  version INTEGER DEFAULT 1,
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
            conn.commit()
        self._logger.info("db_migrated", extra={"path": self.path})

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cur.fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")

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

    def get_request_by_dedupe_hash(self, dedupe_hash: str) -> dict | None:
        row = self.fetchone("SELECT * FROM requests WHERE dedupe_hash = ?", (dedupe_hash,))
        return dict(row) if row else None

    def get_crawl_result_by_request(self, request_id: int) -> dict | None:
        row = self.fetchone("SELECT * FROM crawl_results WHERE request_id = ?", (request_id,))
        return dict(row) if row else None

    def get_summary_by_request(self, request_id: int) -> dict | None:
        row = self.fetchone("SELECT * FROM summaries WHERE request_id = ?", (request_id,))
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
        route_version: int = 1,
    ) -> int:
        sql = (
            "INSERT INTO requests (type, status, correlation_id, chat_id, user_id, input_url, normalized_url, dedupe_hash, "
            "input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected, route_version) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                    route_version,
                ),
            )
            conn.commit()
            rid = int(cur.lastrowid)
            self._logger.info("request_created", extra={"id": rid, "type": type_, "status": status, "cid": correlation_id})
            return rid

    def update_request_status(self, request_id: int, status: str) -> None:
        self.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        self._logger.info("request_status", extra={"id": request_id, "status": status})

    def update_request_correlation_id(self, request_id: int, correlation_id: str) -> None:
        self.execute("UPDATE requests SET correlation_id = ? WHERE id = ?", (correlation_id, request_id))
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
            mid = int(cur.lastrowid)
            self._logger.debug("telegram_snapshot_inserted", extra={"request_id": request_id, "row_id": mid})
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
            "content_markdown, content_html, structured_json, metadata_json, links_json, screenshots_paths_json, "
            "raw_response_json, latency_ms, error_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
            cid = int(cur.lastrowid)
            self._logger.debug("crawl_result_inserted", extra={"request_id": request_id, "row_id": cid, "status": status})
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
    ) -> int:
        sql = (
            "INSERT INTO llm_calls (request_id, provider, model, endpoint, request_headers_json, request_messages_json, "
            "response_text, response_json, tokens_prompt, tokens_completion, cost_usd, latency_ms, status, error_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
                ),
            )
            conn.commit()
            lid = int(cur.lastrowid)
            self._logger.debug("llm_call_inserted", extra={"request_id": request_id, "row_id": lid, "status": status})
            return lid

    def insert_summary(
        self,
        *,
        request_id: int,
        lang: str,
        json_payload: str,
        version: int = 1,
    ) -> int:
        sql = (
            "INSERT INTO summaries (request_id, lang, json_payload, version) VALUES (?, ?, ?, ?)"
        )
        with self.connect() as conn:
            cur = conn.execute(sql, (request_id, lang, json_payload, version))
            conn.commit()
            sid = int(cur.lastrowid)
            self._logger.info("summary_inserted", extra={"request_id": request_id, "version": version})
            return sid

    def upsert_summary(self, *, request_id: int, lang: str, json_payload: str) -> int:
        existing = self.get_summary_by_request(request_id)
        if existing:
            new_version = int(existing.get("version", 1)) + 1
            sql = "UPDATE summaries SET lang = ?, json_payload = ?, version = ?, created_at = CURRENT_TIMESTAMP WHERE request_id = ?"
            with self.connect() as conn:
                conn.execute(sql, (lang, json_payload, new_version, request_id))
                conn.commit()
            self._logger.info("summary_updated", extra={"request_id": request_id, "version": new_version})
            return new_version
        else:
            return self.insert_summary(request_id=request_id, lang=lang, json_payload=json_payload, version=1)

    def insert_audit_log(self, *, level: str, event: str, details_json: str | None = None) -> int:
        sql = "INSERT INTO audit_logs (level, event, details_json) VALUES (?, ?, ?)"
        with self.connect() as conn:
            cur = conn.execute(sql, (level, event, details_json))
            conn.commit()
            aid = int(cur.lastrowid)
            self._logger.debug("audit_logged", extra={"id": aid, "event": event, "level": level})
            return aid
