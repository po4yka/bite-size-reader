"""Add attachment_processing table for image and PDF processing.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-04
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = {
        row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    }
    if "attachment_processing" in tables:
        return
    op.execute(
        text("""
        CREATE TABLE IF NOT EXISTS attachment_processing (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id              INTEGER NOT NULL UNIQUE
                                        REFERENCES requests(id) ON DELETE CASCADE,
            file_type               TEXT NOT NULL,
            mime_type               TEXT,
            file_name               TEXT,
            file_size_bytes         INTEGER,
            page_count              INTEGER,
            extracted_text_length   INTEGER,
            vision_used             INTEGER NOT NULL DEFAULT 0,
            vision_pages_count      INTEGER,
            processing_method       TEXT,
            status                  TEXT NOT NULL DEFAULT 'pending',
            error_text              TEXT,
            created_at              DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_attachment_processing_status"
            " ON attachment_processing(status)"
        )
    )
    op.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_attachment_processing_created_at"
            " ON attachment_processing(created_at)"
        )
    )


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS attachment_processing"))
