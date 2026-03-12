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

USER_ID = 400_001
EDITOR_ID = 400_002
INVITEE_ID = 400_003
JWT_SECRET = "0123456789abcdef0123456789abcdef"
BOT_TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
PRESEEDED_INVITE_TOKEN = "invite-token-parity"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


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
            deleted_at TEXT NULL,
            updated_at TEXT NULL,
            created_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS llm_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
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
            created_at TEXT NULL,
            updated_at TEXT NULL,
            server_version INTEGER NULL,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NULL,
            parent_id INTEGER NULL,
            position INTEGER NULL,
            server_version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_shared INTEGER NOT NULL DEFAULT 0,
            share_count INTEGER NOT NULL DEFAULT 0,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS collection_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL,
            summary_id INTEGER NOT NULL,
            position INTEGER NULL,
            created_at TEXT NOT NULL,
            UNIQUE(collection_id, summary_id)
        );

        CREATE TABLE IF NOT EXISTS collection_collaborators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            invited_by_id INTEGER NULL,
            server_version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(collection_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS collection_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL,
            expires_at TEXT NULL,
            used_at TEXT NULL,
            invited_email TEXT NULL,
            invited_user_id INTEGER NULL,
            status TEXT NOT NULL DEFAULT 'active',
            server_version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def seed_data(connection: sqlite3.Connection) -> None:
    created_at = "2026-03-01T12:00:00Z"
    updated_at = "2026-03-01T12:05:00Z"

    connection.executemany(
        """
        INSERT INTO users (
            telegram_user_id, username, is_owner, server_version, updated_at, created_at
        ) VALUES (?, ?, 0, ?, ?, ?)
        """,
        [
            (USER_ID, "sync_owner", 1, updated_at, created_at),
            (EDITOR_ID, "sync_editor", 2, updated_at, created_at),
            (INVITEE_ID, "sync_invitee", 3, updated_at, created_at),
        ],
    )

    connection.execute(
        """
        INSERT INTO requests (
            id, created_at, updated_at, type, status, correlation_id, user_id,
            input_url, normalized_url, dedupe_hash, lang_detected, route_version, server_version
        ) VALUES (?, ?, ?, 'url', 'completed', 'cid-sync-1', ?, ?, ?, ?, 'en', 1, 10)
        """,
        (
            1,
            created_at,
            updated_at,
            USER_ID,
            "https://example.com/one",
            "https://example.com/one",
            "hash-one",
        ),
    )
    connection.execute(
        """
        INSERT INTO requests (
            id, created_at, updated_at, type, status, correlation_id, user_id,
            input_url, normalized_url, dedupe_hash, lang_detected, route_version, server_version
        ) VALUES (?, ?, ?, 'url', 'pending', 'cid-sync-2', ?, ?, ?, ?, 'en', 1, 20)
        """,
        (
            2,
            "2026-03-01T12:06:00Z",
            "2026-03-01T12:06:00Z",
            USER_ID,
            "https://example.com/two",
            "https://example.com/two",
            "hash-two",
        ),
    )

    connection.execute(
        """
        INSERT INTO summaries (
            id, request_id, lang, json_payload, version, server_version, is_read,
            is_favorited, is_deleted, deleted_at, updated_at, created_at
        ) VALUES (?, ?, 'en', ?, 1, 30, 0, 0, 0, NULL, ?, ?)
        """,
        (
            1,
            1,
            json_payload("Article One"),
            updated_at,
            created_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO summaries (
            id, request_id, lang, json_payload, version, server_version, is_read,
            is_favorited, is_deleted, deleted_at, updated_at, created_at
        ) VALUES (?, ?, 'en', ?, 1, 31, 0, 0, 1, ?, ?, ?)
        """,
        (
            2,
            2,
            json_payload("Article Two"),
            updated_at,
            updated_at,
            created_at,
        ),
    )

    connection.execute(
        """
        INSERT INTO crawl_results (
            request_id, source_url, endpoint, http_status, status, content_markdown,
            metadata_json, latency_ms, server_version, is_deleted, updated_at, created_at
        ) VALUES (?, ?, '/v1/scrape', 200, 'success', ?, ?, 120, 40, 0, ?, ?)
        """,
        (
            1,
            "https://example.com/one",
            "# Heading\n\nBody",
            '{"title":"Article One"}',
            updated_at,
            created_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO llm_calls (
            request_id, provider, model, endpoint, tokens_prompt, tokens_completion,
            cost_usd, latency_ms, status, created_at, updated_at, server_version, is_deleted
        ) VALUES (?, 'openrouter', 'google/gemini-3-flash-preview', '/chat/completions',
                  120, 45, 0.0021, 340, 'completed', ?, ?, 50, 0)
        """,
        (1, created_at, updated_at),
    )

    connection.execute(
        """
        INSERT INTO collections (
            id, user_id, name, description, parent_id, position, server_version,
            updated_at, created_at, is_shared, share_count, is_deleted
        ) VALUES (?, ?, 'Root', 'Shared root', NULL, 1, 60, ?, ?, 1, 1, 0)
        """,
        (1, USER_ID, updated_at, created_at),
    )
    connection.execute(
        """
        INSERT INTO collections (
            id, user_id, name, description, parent_id, position, server_version,
            updated_at, created_at, is_shared, share_count, is_deleted
        ) VALUES (?, ?, 'Child', 'Nested child', ?, 1, 61, ?, ?, 0, 0, 0)
        """,
        (2, USER_ID, 1, updated_at, created_at),
    )
    connection.execute(
        """
        INSERT INTO collection_items (collection_id, summary_id, position, created_at)
        VALUES (1, 1, 1, ?)
        """,
        (created_at,),
    )
    connection.execute(
        """
        INSERT INTO collection_collaborators (
            collection_id, user_id, role, status, invited_by_id, server_version, created_at, updated_at
        ) VALUES (1, ?, 'editor', 'active', ?, 62, ?, ?)
        """,
        (EDITOR_ID, USER_ID, created_at, updated_at),
    )
    connection.execute(
        """
        INSERT INTO collection_invites (
            collection_id, token, role, expires_at, used_at, invited_email, invited_user_id,
            status, server_version, created_at, updated_at
        ) VALUES (1, ?, 'viewer', NULL, NULL, NULL, NULL, 'active', 63, ?, ?)
        """,
        (PRESEEDED_INVITE_TOKEN, created_at, updated_at),
    )
    connection.commit()


def json_payload(title: str) -> str:
    return (
        "{"
        f'"summary_250":"{title} short",'
        f'"summary_1000":"{title} long",'
        f'"tldr":"{title} tl;dr",'
        '"key_ideas":["Idea"],'
        '"topic_tags":["rust","sync"],'
        '"entities":{"people":[],"organizations":[],"locations":[]},'
        '"estimated_reading_time_min":4,'
        '"key_stats":[],'
        '"answered_questions":[],'
        '"seo_keywords":[],'
        f'"metadata":{{"title":"{title}","domain":"example.com"}},'
        '"confidence":0.9,'
        '"hallucination_risk":"low"'
        "}"
    )


def build_env(db_path: Path, port: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DB_PATH": str(db_path),
            "JWT_SECRET_KEY": JWT_SECRET,
            "ALLOWED_USER_IDS": f"{USER_ID},{EDITOR_ID},{INVITEE_ID}",
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
            "SYNC_EXPIRY_HOURS": "1",
            "SYNC_DEFAULT_LIMIT": "200",
            "SYNC_MIN_LIMIT": "1",
            "SYNC_MAX_LIMIT": "500",
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


def normalize_payload(kind: str, payload: Any) -> Any:
    normalized = copy.deepcopy(payload)
    if not isinstance(normalized, dict):
        return normalized
    normalized.pop("meta", None)
    data = normalized.get("data")
    if not isinstance(data, dict):
        return normalized

    if kind == "sync-session":
        data.pop("sessionId", None)
        data.pop("expiresAt", None)
    elif kind in {"sync-full", "sync-delta", "sync-apply"}:
        data.pop("sessionId", None)
    return normalized


def compare_json(
    label: str,
    python_response: Any,
    rust_response: httpx.Response,
    *,
    kind: str,
) -> None:
    if python_response.status_code != rust_response.status_code:
        raise AssertionError(
            f"{label}: status mismatch python={python_response.status_code} rust={rust_response.status_code}"
        )

    normalized_python = normalize_payload(kind, python_response.json())
    normalized_rust = normalize_payload(kind, rust_response.json())
    if normalized_python != normalized_rust:
        raise AssertionError(
            f"{label}: payload mismatch\npython={normalized_python}\nrust={normalized_rust}"
        )


def install_chromadb_stub() -> None:
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


def main() -> int:
    root = repo_root()
    sys.path.insert(0, str(root))

    from tests.rust_bridge_helpers import ensure_rust_binary

    with tempfile.TemporaryDirectory(prefix="m8-sync-collections-") as temp_dir:
        temp_path = Path(temp_dir)
        python_db = temp_path / "python.db"
        rust_db = temp_path / "rust.db"

        for db_path in (python_db, rust_db):
            connection = sqlite3.connect(db_path)
            try:
                init_schema(connection)
                seed_data(connection)
            finally:
                connection.close()

        port = allocate_port()
        python_env = build_env(python_db, port)
        rust_env = build_env(rust_db, port)
        os.environ.update(python_env)
        install_chromadb_stub()

        from fastapi.testclient import TestClient

        from app.api.main import app as python_app
        from app.api.routers.auth.tokens import create_access_token

        owner_headers = {
            "Authorization": f"Bearer {create_access_token(USER_ID, username='sync_owner', client_id='test-client')}"
        }
        invitee_headers = {
            "Authorization": f"Bearer {create_access_token(INVITEE_ID, username='sync_invitee', client_id='test-client')}"
        }

        binary_path = ensure_rust_binary("bsr-api", "bsr-mobile-api")
        rust_process = subprocess.Popen(
            [str(binary_path)],
            cwd=root,
            env=rust_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base_url = f"http://127.0.0.1:{port}"
            wait_for_rust_server(base_url)

            with (
                TestClient(python_app) as python_client,
                httpx.Client(base_url=base_url, timeout=10.0) as rust_client,
            ):
                read_corpus = [
                    ("collections-list", "GET", "/v1/collections", owner_headers, None, "default"),
                    (
                        "collections-acl",
                        "GET",
                        "/v1/collections/1/acl",
                        owner_headers,
                        None,
                        "default",
                    ),
                    (
                        "collection-items",
                        "GET",
                        "/v1/collections/1/items?limit=50&offset=0",
                        owner_headers,
                        None,
                        "default",
                    ),
                ]
                for label, method, path, headers, body, kind in read_corpus:
                    kwargs = {"headers": headers}
                    if body is not None:
                        kwargs["json"] = body
                    python_response = python_client.request(method, path, **kwargs)
                    rust_response = rust_client.request(method, path, **kwargs)
                    compare_json(label, python_response, rust_response, kind=kind)
                    print(f"[ok] {label}")

                python_session = python_client.post(
                    "/v1/sync/sessions",
                    headers=owner_headers,
                    json={"limit": 2},
                )
                rust_session = rust_client.post(
                    "/v1/sync/sessions",
                    headers=owner_headers,
                    json={"limit": 2},
                )
                compare_json("sync-session", python_session, rust_session, kind="sync-session")
                print("[ok] sync-session")

                python_session_id = python_session.json()["data"]["sessionId"]
                rust_session_id = rust_session.json()["data"]["sessionId"]

                python_full = python_client.get(
                    f"/v1/sync/full?session_id={python_session_id}&limit=2",
                    headers=owner_headers,
                )
                rust_full = rust_client.get(
                    f"/v1/sync/full?session_id={rust_session_id}&limit=2",
                    headers=owner_headers,
                )
                compare_json("sync-full", python_full, rust_full, kind="sync-full")
                print("[ok] sync-full")

                python_delta = python_client.get(
                    f"/v1/sync/delta?session_id={python_session_id}&since=0&limit=20",
                    headers=owner_headers,
                )
                rust_delta = rust_client.get(
                    f"/v1/sync/delta?session_id={rust_session_id}&since=0&limit=20",
                    headers=owner_headers,
                )
                compare_json("sync-delta", python_delta, rust_delta, kind="sync-delta")
                print("[ok] sync-delta")

                apply_body_python = {
                    "session_id": python_session_id,
                    "changes": [
                        {
                            "entity_type": "summary",
                            "id": 1,
                            "action": "update",
                            "last_seen_version": 30,
                            "payload": {"is_read": True},
                        },
                        {
                            "entity_type": "summary",
                            "id": 2,
                            "action": "delete",
                            "last_seen_version": 31,
                            "payload": {},
                        },
                    ],
                }
                apply_body_rust = copy.deepcopy(apply_body_python)
                apply_body_rust["session_id"] = rust_session_id

                python_apply = python_client.post(
                    "/v1/sync/apply",
                    headers=owner_headers,
                    json=apply_body_python,
                )
                rust_apply = rust_client.post(
                    "/v1/sync/apply",
                    headers=owner_headers,
                    json=apply_body_rust,
                )
                compare_json("sync-apply", python_apply, rust_apply, kind="sync-apply")
                print("[ok] sync-apply")

                python_accept = python_client.post(
                    f"/v1/collections/invites/{PRESEEDED_INVITE_TOKEN}/accept",
                    headers=invitee_headers,
                )
                rust_accept = rust_client.post(
                    f"/v1/collections/invites/{PRESEEDED_INVITE_TOKEN}/accept",
                    headers=invitee_headers,
                )
                compare_json(
                    "collections-accept-invite", python_accept, rust_accept, kind="default"
                )
                print("[ok] collections-accept-invite")
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
