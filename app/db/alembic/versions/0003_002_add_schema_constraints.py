"""Add schema integrity constraints: NOT NULL on llm_calls.request_id, validation triggers.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

_LLM_CALLS_DDL = """
    CREATE TABLE llm_calls_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        provider TEXT,
        model TEXT,
        endpoint TEXT,
        request_headers_json TEXT,
        request_messages_json TEXT,
        response_text TEXT,
        response_json TEXT,
        openrouter_response_text TEXT,
        openrouter_response_json TEXT,
        tokens_prompt INTEGER,
        tokens_completion INTEGER,
        cost_usd REAL,
        latency_ms INTEGER,
        status TEXT,
        error_text TEXT,
        structured_output_used INTEGER,
        structured_output_mode TEXT,
        error_context_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        server_version INTEGER,
        is_deleted INTEGER DEFAULT 0,
        deleted_at DATETIME,
        FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE
    )
"""

_VALIDATE_INSERT_TRIGGER = """
    CREATE TRIGGER validate_request_insert
    BEFORE INSERT ON requests
    WHEN (
        (NEW.type = 'url' AND NEW.normalized_url IS NULL)
        OR (NEW.type = 'forward' AND (
            (NEW.fwd_from_chat_id IS NOT NULL AND NEW.fwd_from_msg_id IS NULL)
            OR (NEW.fwd_from_chat_id IS NULL AND NEW.fwd_from_msg_id IS NOT NULL)
        ))
    )
    BEGIN
        SELECT RAISE(ABORT, 'Request validation failed');
    END
"""

_VALIDATE_UPDATE_TRIGGER = """
    CREATE TRIGGER validate_request_update
    BEFORE UPDATE ON requests
    WHEN (
        (NEW.type = 'url' AND NEW.normalized_url IS NULL)
        OR (NEW.type = 'forward' AND (
            (NEW.fwd_from_chat_id IS NOT NULL AND NEW.fwd_from_msg_id IS NULL)
            OR (NEW.fwd_from_chat_id IS NULL AND NEW.fwd_from_msg_id IS NOT NULL)
        ))
    )
    BEGIN
        SELECT RAISE(ABORT, 'Request validation failed');
    END
"""

_LLM_INDEXES = [
    ("idx_llm_calls_request", "request_id, created_at"),
    ("idx_llm_calls_status", "status, created_at"),
    ("idx_llm_calls_model", "model, created_at"),
    ("idx_llm_calls_provider_model", "provider, model, created_at"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Remove orphaned llm_calls (no valid request)
    conn.execute(text("""
        DELETE FROM llm_calls
        WHERE request_id IS NULL
           OR request_id NOT IN (SELECT id FROM requests)
    """))

    # Recreate llm_calls with NOT NULL on request_id
    op.execute(text(_LLM_CALLS_DDL))
    conn.execute(text("INSERT INTO llm_calls_new SELECT * FROM llm_calls"))
    conn.execute(text("DROP TABLE llm_calls"))
    conn.execute(text("ALTER TABLE llm_calls_new RENAME TO llm_calls"))
    for idx_name, cols in _LLM_INDEXES:
        op.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON llm_calls({cols})"))

    # Add validation triggers
    conn.execute(text("DROP TRIGGER IF EXISTS validate_request_insert"))
    conn.execute(text("DROP TRIGGER IF EXISTS validate_request_update"))
    op.execute(text(_VALIDATE_INSERT_TRIGGER))
    op.execute(text(_VALIDATE_UPDATE_TRIGGER))


def downgrade() -> None:
    conn = op.get_bind()

    # Remove triggers
    conn.execute(text("DROP TRIGGER IF EXISTS validate_request_insert"))
    conn.execute(text("DROP TRIGGER IF EXISTS validate_request_update"))

    # Recreate llm_calls with nullable request_id
    op.execute(text("""
        CREATE TABLE llm_calls_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            provider TEXT, model TEXT, endpoint TEXT,
            request_headers_json TEXT, request_messages_json TEXT,
            response_text TEXT, response_json TEXT,
            openrouter_response_text TEXT, openrouter_response_json TEXT,
            tokens_prompt INTEGER, tokens_completion INTEGER,
            cost_usd REAL, latency_ms INTEGER, status TEXT, error_text TEXT,
            structured_output_used INTEGER, structured_output_mode TEXT,
            error_context_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            server_version INTEGER, is_deleted INTEGER DEFAULT 0, deleted_at DATETIME,
            FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE SET NULL
        )
    """))
    conn.execute(text("INSERT INTO llm_calls_old SELECT * FROM llm_calls"))
    conn.execute(text("DROP TABLE llm_calls"))
    conn.execute(text("ALTER TABLE llm_calls_old RENAME TO llm_calls"))
    for idx_name, cols in _LLM_INDEXES:
        op.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON llm_calls({cols})"))
