"""Add attachment_processing table for image and PDF processing.

This migration creates the attachment_processing table which tracks
image and PDF attachment processing jobs, including file metadata,
extraction details, and processing status.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def upgrade(db: DatabaseSessionManager) -> None:
    """Create the attachment_processing table."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    if "attachment_processing" in db_instance.get_tables():
        logger.info("attachment_processing_table_exists_skipping")
        return

    db_instance.execute_sql("""
        CREATE TABLE IF NOT EXISTS attachment_processing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_name TEXT,
            file_size_bytes INTEGER,
            page_count INTEGER,
            extracted_text_length INTEGER,
            vision_used INTEGER NOT NULL DEFAULT 0,
            vision_pages_count INTEGER,
            processing_method TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_text TEXT,
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)

    db_instance.execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_attachment_processing_status ON attachment_processing(status)"
    )
    db_instance.execute_sql(
        "CREATE INDEX IF NOT EXISTS idx_attachment_processing_created_at ON attachment_processing(created_at)"
    )

    logger.info("attachment_processing_table_created")


def downgrade(db: DatabaseSessionManager) -> None:
    """Drop the attachment_processing table."""
    db_instance = getattr(db, "database", getattr(db, "_database", None))
    if db_instance is None:
        msg = "Cannot resolve database instance from db object"
        raise TypeError(msg)

    db_instance.execute_sql("DROP TABLE IF EXISTS attachment_processing")
    logger.info("attachment_processing_table_dropped")
