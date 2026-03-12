from __future__ import annotations

import copy
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import httpx


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


USER_ID = 123_456_789
JWT_SECRET = "0123456789abcdef0123456789abcdef"
BOT_TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


def allocate_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id INTEGER PRIMARY KEY,
            username TEXT NULL,
            is_owner INTEGER NOT NULL DEFAULT 0,
            preferences_json TEXT NULL,
            linked_telegram_user_id INTEGER NULL,
            linked_telegram_username TEXT NULL,
            linked_telegram_photo_url TEXT NULL,
            linked_telegram_first_name TEXT NULL,
            linked_telegram_last_name TEXT NULL,
            linked_at TEXT NULL,
            link_nonce TEXT NULL,
            link_nonce_expires_at TEXT NULL,
            server_version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            type TEXT NULL,
            status TEXT NULL,
            correlation_id TEXT NULL,
            chat_id INTEGER NULL,
            user_id INTEGER NULL,
            input_url TEXT NULL,
            normalized_url TEXT NULL,
            dedupe_hash TEXT NULL,
            input_message_id INTEGER NULL,
            fwd_from_chat_id INTEGER NULL,
            fwd_from_msg_id INTEGER NULL,
            lang_detected TEXT NULL,
            content_text TEXT NULL,
            route_version INTEGER NOT NULL DEFAULT 1,
            server_version INTEGER NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL,
            error_type TEXT NULL,
            error_message TEXT NULL,
            error_timestamp TEXT NULL,
            processing_time_ms INTEGER NULL,
            error_context_json TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL UNIQUE,
            lang TEXT NULL,
            json_payload TEXT NULL,
            insights_json TEXT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            server_version INTEGER NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            is_favorited INTEGER NOT NULL DEFAULT 0,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL,
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crawl_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            source_url TEXT NULL,
            endpoint TEXT NULL,
            http_status INTEGER NULL,
            status TEXT NULL,
            options_json TEXT NULL,
            correlation_id TEXT NULL,
            content_markdown TEXT NULL,
            content_html TEXT NULL,
            structured_json TEXT NULL,
            metadata_json TEXT NULL,
            links_json TEXT NULL,
            screenshots_paths_json TEXT NULL,
            firecrawl_success INTEGER NULL,
            firecrawl_error_code TEXT NULL,
            firecrawl_error_message TEXT NULL,
            firecrawl_details_json TEXT NULL,
            raw_response_json TEXT NULL,
            latency_ms INTEGER NULL,
            error_text TEXT NULL,
            server_version INTEGER NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            provider TEXT NULL,
            model TEXT NULL,
            endpoint TEXT NULL,
            request_headers_json TEXT NULL,
            request_messages_json TEXT NULL,
            response_text TEXT NULL,
            response_json TEXT NULL,
            openrouter_response_text TEXT NULL,
            openrouter_response_json TEXT NULL,
            tokens_prompt INTEGER NULL,
            tokens_completion INTEGER NULL,
            cost_usd REAL NULL,
            latency_ms INTEGER NULL,
            status TEXT NULL,
            error_text TEXT NULL,
            structured_output_used INTEGER NULL,
            structured_output_mode TEXT NULL,
            error_context_json TEXT NULL,
            created_at TEXT NOT NULL,
            server_version INTEGER NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS user_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            platform TEXT NOT NULL,
            device_id TEXT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT NULL,
            created_at TEXT NULL
        );
        """
    )


def seed_data(connection: sqlite3.Connection) -> None:
    created_at = "2026-03-01T12:00:00Z"
    updated_at = "2026-03-01T12:05:00Z"
    connection.execute(
        """
        INSERT INTO users (
            telegram_user_id, username, is_owner, server_version, updated_at, created_at
        ) VALUES (?, ?, 0, 1, ?, ?)
        """,
        (USER_ID, "parity_user", updated_at, created_at),
    )
    connection.execute(
        """
        INSERT INTO requests (
            id, created_at, updated_at, type, status, correlation_id, user_id,
            input_url, normalized_url, dedupe_hash, lang_detected, route_version
        ) VALUES (?, ?, ?, 'url', 'ok', 'cid-article-1', ?, ?, ?, ?, 'en', 1)
        """,
        (
            1,
            created_at,
            updated_at,
            USER_ID,
            "https://example.com/article",
            "https://example.com/article",
            "f4d6b66ccbe4dbaf26e6fc6f3d834e4f222e99e9ddc0b8f2d4f7b38d0d0e1f71",
        ),
    )
    connection.execute(
        """
        INSERT INTO summaries (
            id, request_id, lang, json_payload, version, server_version, is_read, is_favorited,
            is_deleted, updated_at, created_at
        ) VALUES (?, ?, 'en', ?, 1, 1, 0, 0, 0, ?, ?)
        """,
        (
            1,
            1,
            """{
                "summary_250": "Short summary",
                "summary_1000": "Long summary",
                "tldr": "Too long",
                "key_ideas": ["Idea 1", "Idea 2"],
                "topic_tags": ["tag1", "tag2"],
                "entities": {"people": ["Person"], "organizations": ["Org"], "locations": ["Loc"]},
                "estimated_reading_time_min": 5,
                "key_stats": [{"label": "Stat", "value": 10, "unit": "%", "source_excerpt": "source"}],
                "answered_questions": ["Q1?"],
                "readability": {"method": "FK", "score": 50.0, "level": "Easy"},
                "seo_keywords": ["keyword"],
                "metadata": {
                    "title": "Example Article",
                    "domain": "example.com",
                    "author": "Author",
                    "published_at": "2023-01-01"
                },
                "confidence": 0.9,
                "hallucination_risk": "low"
            }""",
            updated_at,
            created_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO crawl_results (
            request_id, updated_at, source_url, endpoint, http_status, status,
            content_markdown, metadata_json, latency_ms, server_version, is_deleted
        ) VALUES (?, ?, ?, '/v1/scrape', 200, 'success', ?, ?, 120, 1, 0)
        """,
        (
            1,
            updated_at,
            "https://example.com/article",
            "# Heading\n\nBody text.",
            '{"title":"Example Article","domain":"example.com","author":"Author"}',
        ),
    )
    connection.execute(
        """
        INSERT INTO llm_calls (
            request_id, updated_at, provider, model, endpoint, tokens_prompt, tokens_completion,
            cost_usd, latency_ms, status, created_at, server_version, is_deleted
        ) VALUES (?, ?, 'openrouter', 'google/gemini-3-flash-preview', '/chat/completions',
                  120, 45, 0.0021, 340, 'completed', ?, 1, 0)
        """,
        (1, updated_at, created_at),
    )
    connection.execute(
        """
        INSERT INTO requests (
            id, created_at, updated_at, type, status, correlation_id, user_id,
            input_url, normalized_url, dedupe_hash, lang_detected, route_version
        ) VALUES (?, ?, ?, 'url', 'pending', 'cid-pending-1', ?, ?, ?, ?, 'en', 1)
        """,
        (
            2,
            "2026-03-01T12:10:00Z",
            "2026-03-01T12:10:00Z",
            USER_ID,
            "https://example.com/pending",
            "https://example.com/pending",
            "67a91c75d775bb03ffb8eb80fd1f3cb2112292a6cc72cf872f29ac6eaddf37c9",
        ),
    )
    connection.commit()


def build_env(db_path: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DB_PATH": str(db_path),
            "JWT_SECRET_KEY": JWT_SECRET,
            "ALLOWED_USER_IDS": str(USER_ID),
            "ALLOWED_CLIENT_IDS": "test-client,webapp",
            "REDIS_ENABLED": "0",
            "REDIS_REQUIRED": "0",
            "API_HOST": "127.0.0.1",
            "API_PORT": str(port),
            "BOT_TOKEN": BOT_TOKEN,
            "API_ID": "123456",
            "API_HASH": "0123456789abcdef0123456789abcdef",
            "OPENROUTER_API_KEY": "sk-or-v1-parity-test",
            "APP_VERSION": "1.0.0",
            "APP_BUILD": "parity-test",
        }
    )
    return env


def wait_for_rust_server(base_url: str, timeout_sec: float = 20.0) -> None:
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception as err:  # pragma: no cover - startup polling
            last_error = err
        time.sleep(0.2)
    raise RuntimeError(f"Rust API server did not become ready: {last_error}")


def normalize_payload(path: str, payload: Any) -> Any:
    normalized = copy.deepcopy(payload)
    if isinstance(normalized, dict):
        normalized.pop("meta", None)
        data = normalized.get("data")
        if isinstance(data, dict) and path.endswith("/status"):
            data.pop("updatedAt", None)
        if isinstance(data, dict) and path == "/v1/requests" and data.get("isDuplicate"):
            data.pop("summarizedAt", None)
    return normalized


def compare_response(
    label: str,
    path: str,
    python_response: Any,
    rust_response: httpx.Response,
    *,
    bare_json: bool = False,
) -> None:
    if python_response.status_code != rust_response.status_code:
        raise AssertionError(
            f"{label}: status mismatch python={python_response.status_code} rust={rust_response.status_code}"
        )

    python_payload = python_response.json()
    rust_payload = rust_response.json()
    if bare_json:
        if python_payload != rust_payload:
            raise AssertionError(
                f"{label}: bare JSON mismatch\npython={python_payload}\nrust={rust_payload}"
            )
        return

    normalized_python = normalize_payload(path, python_payload)
    normalized_rust = normalize_payload(path, rust_payload)
    if normalized_python != normalized_rust:
        raise AssertionError(
            f"{label}: payload mismatch\npython={normalized_python}\nrust={normalized_rust}"
        )


def main() -> int:
    root = repo_root()
    sys.path.insert(0, str(root))

    from tests.rust_bridge_helpers import ensure_rust_binary

    with tempfile.TemporaryDirectory(prefix="m8-content-parity-") as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "parity.db"
        connection = sqlite3.connect(db_path)
        try:
            init_schema(connection)
            seed_data(connection)
        finally:
            connection.close()

        port = allocate_port()
        env = build_env(db_path, port)
        os.environ.update(env)

        chromadb_module = types.ModuleType("chromadb")

        class DummySettings:
            def __init__(self, **_: Any) -> None:
                pass

        class DummyCollection:
            def upsert(self, **_: Any) -> None:
                return None

            def query(self, **_: Any) -> dict[str, list[Any]]:
                return {"ids": [[]], "metadatas": [[]], "distances": [[]], "documents": [[]]}

            def delete(self, **_: Any) -> None:
                return None

        class DummyHttpClient:
            def __init__(self, **_: Any) -> None:
                self._collection = DummyCollection()

            def heartbeat(self) -> int:
                return 1

            def get_or_create_collection(self, **_: Any) -> DummyCollection:
                return self._collection

        class DummyChromaError(Exception):
            pass

        cast("Any", chromadb_module).Settings = DummySettings
        cast("Any", chromadb_module).HttpClient = DummyHttpClient
        chromadb_errors = types.ModuleType("chromadb.errors")
        cast("Any", chromadb_errors).ChromaError = DummyChromaError
        sys.modules.setdefault("chromadb", chromadb_module)
        sys.modules.setdefault("chromadb.errors", chromadb_errors)

        from fastapi.testclient import TestClient

        from app.api.main import app as python_app
        from app.api.routers.auth.tokens import create_access_token

        token = create_access_token(USER_ID, username="parity_user", client_id="test-client")
        auth_headers = {"Authorization": f"Bearer {token}"}

        binary_path = ensure_rust_binary("bsr-api", "bsr-mobile-api")
        rust_process = subprocess.Popen(
            [str(binary_path)],
            cwd=root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            wait_for_rust_server(base_url)

            corpus = [
                ("article-detail", "GET", "/v1/articles/1", None, False),
                ("summary-content", "GET", "/v1/summaries/1/content?format=text", None, False),
                ("request-status", "GET", "/v1/requests/2/status", None, False),
                (
                    "notification-register",
                    "POST",
                    "/v1/notifications/device",
                    {
                        "token": "fcm_token_parity",
                        "platform": "android",
                        "device_id": "device_parity",
                    },
                    True,
                ),
            ]

            with (
                TestClient(python_app) as python_client,
                httpx.Client(base_url=base_url, timeout=10.0) as rust_client,
            ):
                for label, method, path, body, bare_json in corpus:
                    request_kwargs = {"headers": auth_headers}
                    if body is not None:
                        request_kwargs["json"] = body
                    python_response = python_client.request(method, path, **request_kwargs)
                    rust_response = rust_client.request(method, path, **request_kwargs)
                    compare_response(
                        label,
                        path,
                        python_response,
                        rust_response,
                        bare_json=bare_json,
                    )
                    print(f"[ok] {label}")
        finally:
            rust_process.terminate()
            try:
                rust_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                rust_process.kill()
                rust_process.wait(timeout=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
