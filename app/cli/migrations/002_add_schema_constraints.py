"""Add schema integrity constraints for data validation.

This migration adds:
1. NOT NULL constraint on LLMCall.request_id (currently nullable)
2. CHECK constraints to validate request types have required fields
3. Additional data validation constraints

Expected impact: Prevents orphaned LLM calls and invalid request records.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.database import Database
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def upgrade(db: Database | DatabaseSessionManager) -> None:
    """Add schema integrity constraints."""
    logger.info("Starting Phase 2 schema improvements...")

    # Step 1: Check for orphaned LLM calls and clean them up
    logger.info("Step 1: Checking for orphaned LLM calls...")
    orphaned_count = _cleanup_orphaned_llm_calls(db)
    if orphaned_count > 0:
        logger.warning(
            "orphaned_llm_calls_cleaned",
            extra={"count": orphaned_count},
        )

    # Step 2: Recreate llm_calls table with NOT NULL constraint
    logger.info("Step 2: Recreating llm_calls table with NOT NULL constraint...")
    _recreate_llm_calls_table(db)
    logger.info("✓ LLMCall.request is now NOT NULL")

    # Step 3: Add CHECK constraints via triggers
    logger.info("Step 3: Adding CHECK constraints via triggers...")
    _add_request_validation_triggers(db)
    logger.info("✓ Request validation triggers created")

    logger.info("Phase 2 schema improvements completed successfully")


def _cleanup_orphaned_llm_calls(db: Database | DatabaseSessionManager) -> int:
    """Delete any LLM calls without a valid request reference.

    Returns:
        Number of orphaned records deleted
    """
    # Count orphaned records (use direct SQL, already in transaction)
    count_sql = """
        SELECT COUNT(*) FROM llm_calls
        WHERE request_id IS NULL
           OR request_id NOT IN (SELECT id FROM requests)
    """
    cursor = db._database.execute_sql(count_sql)
    result = cursor.fetchone()
    orphaned_count = result[0] if result else 0

    if orphaned_count == 0:
        logger.info("No orphaned LLM calls found")
        return 0

    # Delete orphaned records
    delete_sql = """
        DELETE FROM llm_calls
        WHERE request_id IS NULL
           OR request_id NOT IN (SELECT id FROM requests)
    """
    db._database.execute_sql(delete_sql)

    return orphaned_count


def _recreate_llm_calls_table(db: Database | DatabaseSessionManager) -> None:
    """Recreate llm_calls table with NOT NULL constraint on request_id.

    SQLite doesn't support ALTER COLUMN, so we need to:
    1. Create new table with desired schema
    2. Copy data from old table
    3. Drop old table
    4. Rename new table
    5. Recreate indexes
    """
    # Create new table with NOT NULL constraint
    db._database.execute_sql("""
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
    """)

    # Copy data from old table
    db._database.execute_sql("""
        INSERT INTO llm_calls_new
        SELECT * FROM llm_calls
    """)

    # Drop old table
    db._database.execute_sql("DROP TABLE llm_calls")

    # Rename new table
    db._database.execute_sql("ALTER TABLE llm_calls_new RENAME TO llm_calls")

    # Recreate indexes (they were on the old table)
    indexes = [
        ("idx_llm_calls_request", ["request_id", "created_at"]),
        ("idx_llm_calls_status", ["status", "created_at"]),
        ("idx_llm_calls_model", ["model", "created_at"]),
        ("idx_llm_calls_provider_model", ["provider", "model", "created_at"]),
    ]

    for index_name, columns in indexes:
        cols = ", ".join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON llm_calls({cols})"
        db._database.execute_sql(sql)
        logger.debug(f"  ✓ Recreated index {index_name}")


def _add_request_validation_triggers(db: Database | DatabaseSessionManager) -> None:
    """Add triggers to validate request data based on type.

    Validation rules:
    - URL requests must have normalized_url
    - Forward requests: if fwd_from_chat_id is set, fwd_from_msg_id must also be set
      (and vice versa). Both NULL is valid (user/privacy-protected forwards).
    """
    # Drop existing triggers if they exist
    db._database.execute_sql("DROP TRIGGER IF EXISTS validate_request_insert")
    db._database.execute_sql("DROP TRIGGER IF EXISTS validate_request_update")

    # Trigger for INSERT
    # For forward requests, enforce that chat_id and msg_id are either both set or both NULL.
    # User forwards and privacy-protected forwards legitimately have both as NULL.
    db._database.execute_sql("""
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
            SELECT RAISE(ABORT, 'Request validation failed: URL requests must have normalized_url, forward requests must have both fwd_from_chat_id and fwd_from_msg_id or neither');
        END;
    """)
    logger.debug("  Created INSERT validation trigger")

    # Trigger for UPDATE
    db._database.execute_sql("""
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
            SELECT RAISE(ABORT, 'Request validation failed: URL requests must have normalized_url, forward requests must have both fwd_from_chat_id and fwd_from_msg_id or neither');
        END;
    """)
    logger.debug("  Created UPDATE validation trigger")


def downgrade(db: Database | DatabaseSessionManager) -> None:
    """Remove schema integrity constraints."""
    logger.info("Rolling back Phase 2 schema improvements...")

    # Step 1: Remove validation triggers
    logger.info("Step 1: Removing validation triggers...")
    db._database.execute_sql("DROP TRIGGER IF EXISTS validate_request_insert")
    db._database.execute_sql("DROP TRIGGER IF EXISTS validate_request_update")
    logger.info("✓ Validation triggers removed")

    # Step 2: Recreate llm_calls table with nullable request_id
    logger.info("Step 2: Recreating llm_calls table with nullable request_id...")

    # Create old-style table
    db._database.execute_sql("""
        CREATE TABLE llm_calls_old (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
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
            FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE SET NULL
        )
    """)

    # Copy data back
    db._database.execute_sql("""
        INSERT INTO llm_calls_old
        SELECT * FROM llm_calls
    """)

    # Drop new table
    db._database.execute_sql("DROP TABLE llm_calls")

    # Rename old table
    db._database.execute_sql("ALTER TABLE llm_calls_old RENAME TO llm_calls")

    # Recreate indexes
    indexes = [
        ("idx_llm_calls_request", ["request_id", "created_at"]),
        ("idx_llm_calls_status", ["status", "created_at"]),
        ("idx_llm_calls_model", ["model", "created_at"]),
        ("idx_llm_calls_provider_model", ["provider", "model", "created_at"]),
    ]

    for index_name, columns in indexes:
        cols = ", ".join(columns)
        sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON llm_calls({cols})"
        db._database.execute_sql(sql)

    logger.info("✓ LLMCall.request is now nullable again")
    logger.info("Phase 2 rollback completed")
