#!/usr/bin/env python3
"""Test script to verify database migration framework works correctly."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.database import Database
from app.cli.migrations.migration_runner import MigrationRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_migration_framework():
    """Test the migration framework with in-memory database."""
    logger.info("=" * 60)
    logger.info("Testing Database Migration Framework")
    logger.info("=" * 60)

    # Test 1: Create in-memory database
    logger.info("\n[Test 1] Creating in-memory database...")
    db = Database(path=":memory:")
    db.migrate()
    logger.info("✓ Base schema created")

    # Test 2: Initialize migration runner
    logger.info("\n[Test 2] Initializing migration runner...")
    runner = MigrationRunner(db)
    logger.info("✓ Migration runner initialized")

    # Test 3: Check for pending migrations
    logger.info("\n[Test 3] Checking for pending migrations...")
    pending = runner.get_pending_migrations()
    logger.info(f"Found {len(pending)} pending migration(s):")
    for p in pending:
        logger.info(f"  - {p.stem}")

    # Test 4: Check migration status
    logger.info("\n[Test 4] Checking migration status...")
    status = runner.get_migration_status()
    logger.info(f"Total migrations: {status['total']}")
    logger.info(f"Applied: {status['applied']}")
    logger.info(f"Pending: {status['pending']}")

    # Test 5: Run migrations
    logger.info("\n[Test 5] Running pending migrations...")
    count = runner.run_pending()
    logger.info(f"✓ Applied {count} migration(s)")

    # Test 6: Verify indexes were created
    logger.info("\n[Test 6] Verifying indexes were created...")
    with db._database.connection_context():
        # Check requests table indexes
        indexes = db._database.get_indexes("requests")
        index_names = {idx.name for idx in indexes}
        logger.info(f"Requests table has {len(index_names)} indexes:")
        for name in sorted(index_names):
            logger.info(f"  ✓ {name}")

        # Verify critical indexes exist
        expected_indexes = [
            "idx_requests_correlation_id",
            "idx_requests_user_created",
            "idx_summaries_read_status",
            "idx_llm_calls_request",
        ]

        all_tables_indexes = []
        for table in ["requests", "summaries", "llm_calls", "crawl_results", "audit_logs"]:
            table_indexes = db._database.get_indexes(table)
            all_tables_indexes.extend([idx.name for idx in table_indexes])

        missing = [idx for idx in expected_indexes if idx not in all_tables_indexes]
        if missing:
            logger.error(f"✗ Missing indexes: {missing}")
            return False
        logger.info("✓ All critical indexes created")

    # Test 7: Verify foreign key constraints enabled
    logger.info("\n[Test 7] Verifying foreign key constraints...")
    result = db.fetchone("PRAGMA foreign_keys")
    if result and result[0] == 1:
        logger.info("✓ Foreign key constraints are enabled")
    else:
        logger.error("✗ Foreign key constraints are NOT enabled")
        return False

    logger.info("\n" + "=" * 60)
    logger.info("All tests passed! ✓")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = test_migration_framework()
        sys.exit(0 if success else 1)
    except Exception:
        logger.exception("Test failed with exception")
        sys.exit(1)
