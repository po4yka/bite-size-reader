#!/usr/bin/env python3
"""Test script to verify Phase 2 schema improvements.

Since Database.migrate() now runs all pending migrations (including Phase 2),
this test verifies the constraints are enforced after a standard migration.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

import peewee
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.cli.migrations.migration_runner import MigrationRunner
from app.db.database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_phase2_migration():
    """Test Phase 2 schema constraint improvements.

    Database.migrate() applies all pending migrations automatically,
    so we verify that Phase 2 constraints are active after migration.
    """
    print("=" * 70)
    print("Testing Phase 2: Schema Integrity Improvements")
    print("=" * 70)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print(f"\n-- Using temporary database: {db_path}")

        # Step 1: Create base schema and run all migrations
        print("\n[1] Creating base schema and running all migrations...")
        db = Database(path=db_path)
        db.migrate()

        runner = MigrationRunner(db)

        # Verify that Phase 2 migration was already applied by db.migrate()
        pending = runner.get_pending_migrations()
        phase2_pending = [m for m in pending if "002_" in m.name]
        assert not phase2_pending, "Phase 2 migration should already be applied by db.migrate()"
        print("-- Base schema and all migrations applied (including Phase 2)")

        # Step 2: Insert test data
        print("\n[2] Inserting test data...")

        # Import models
        from app.db.models import LLMCall, Request, User

        # Create a valid user and request using ORM (handles defaults)
        user = User.create(telegram_user_id=123456789, username="testuser", is_owner=True)

        request = Request.create(
            type="url",
            status="ok",
            correlation_id="test-corr-1",
            user_id=user.telegram_user_id,
            normalized_url="https://example.com/test-phase2",
        )

        # Insert a valid LLM call using ORM
        llm_call = LLMCall.create(
            request=request, provider="openrouter", model="qwen/qwen3-max", status="ok"
        )
        assert llm_call.id is not None

        # Verify NOT NULL is enforced on llm_calls.request_id
        with pytest.raises(peewee.IntegrityError):
            db._database.execute_sql("""
                INSERT INTO llm_calls (request_id, provider, model, status)
                VALUES (NULL, 'openrouter', 'qwen/qwen3-max', 'orphaned')
            """)

        result = db.fetchone("SELECT COUNT(*) FROM llm_calls")
        llm_calls_count = result[0]
        print(f"-- Test data created: {llm_calls_count} LLM call(s) (schema enforces NOT NULL)")

        # Step 3: Verify Phase 2 constraints are active
        print("\n[3] Verifying Phase 2 constraints...")

        # Step 3a: Test NOT NULL constraint on LLMCall.request
        print("\n[3a] Testing NOT NULL constraint on LLMCall.request...")
        try:
            db._database.execute_sql("""
                INSERT INTO llm_calls (request_id, provider, model, status)
                VALUES (NULL, 'openrouter', 'qwen/qwen3-max', 'should-fail')
            """)
            print("FAIL: NOT NULL constraint NOT enforced (insert succeeded when it should fail)")
            pytest.fail("NOT NULL constraint not enforced on llm_calls.request_id")
        except Exception as e:
            if "NOT NULL" in str(e) or "constraint" in str(e).lower():
                print("-- NOT NULL constraint enforced (insert correctly rejected)")
            else:
                print(f"FAIL: Unexpected error: {e}")
                pytest.fail(f"Unexpected error testing NOT NULL constraint: {e}")

        # Step 3b: Test CHECK constraint for URL requests
        print("\n[3b] Testing CHECK constraint for URL requests...")
        try:
            # Try to insert URL request without normalized_url
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, created_at, updated_at, server_version, route_version)
                VALUES ('url', 'ok', 'test-invalid-url', 123456789, datetime('now'), datetime('now'), 1, 1)
            """)
            print("FAIL: CHECK constraint NOT enforced for URL requests")
            pytest.fail("URL request CHECK constraint not enforced")
        except Exception as e:
            if "validation" in str(e).lower() or "abort" in str(e).lower():
                print("-- CHECK constraint enforced for URL requests")
            else:
                print(f"FAIL: Unexpected error: {e}")
                pytest.fail(f"Unexpected error testing URL CHECK constraint: {e}")

        # Step 3c: Test CHECK constraint for forward requests
        print("\n[3c] Testing CHECK constraint for forward requests...")
        try:
            # Try to insert forward request without fwd_from_chat_id
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, fwd_from_msg_id, created_at, updated_at, server_version, route_version)
                VALUES ('forward', 'ok', 'test-invalid-forward', 123456789, 999, datetime('now'), datetime('now'), 1, 1)
            """)
            print("FAIL: CHECK constraint NOT enforced for forward requests")
            pytest.fail("Forward request CHECK constraint not enforced")
        except Exception as e:
            if "validation" in str(e).lower() or "abort" in str(e).lower():
                print("-- CHECK constraint enforced for forward requests")
            else:
                print(f"FAIL: Unexpected error: {e}")
                pytest.fail(f"Unexpected error testing forward CHECK constraint: {e}")

        # Step 4: Verify valid requests still work
        print("\n[4] Verifying valid requests still work...")

        # Valid URL request
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, normalized_url, created_at, updated_at, server_version, route_version, is_deleted)
            VALUES ('url', 'ok', 'test-valid-url', 123456789, 'https://valid.com', datetime('now'), datetime('now'), 1, 1, 0)
        """)

        # Valid forward request
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, fwd_from_chat_id, fwd_from_msg_id, created_at, updated_at, server_version, route_version, is_deleted)
            VALUES ('forward', 'ok', 'test-valid-forward', 123456789, -100123456789, 999, datetime('now'), datetime('now'), 1, 1, 0)
        """)

        result = db.fetchone(
            "SELECT COUNT(*) FROM requests WHERE correlation_id LIKE 'test-valid-%'"
        )
        valid_count = result[0]

        if valid_count == 2:
            print("-- Valid requests accepted (2 created)")
        else:
            print(f"FAIL: Expected 2 valid requests, found {valid_count}")
            pytest.fail(f"Expected 2 valid requests, found {valid_count}")

        # Step 5: Verify foreign key CASCADE on LLMCall
        print("\n[5] Verifying CASCADE on DELETE for LLMCall.request...")

        # Create a request with an LLM call
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, normalized_url, created_at, updated_at, server_version, route_version, is_deleted)
            VALUES ('url', 'ok', 'test-cascade', 123456789, 'https://cascade.com', datetime('now'), datetime('now'), 1, 1, 0)
        """)

        result = db.fetchone("SELECT id FROM requests WHERE correlation_id = 'test-cascade'")
        cascade_request_id = result[0]

        db._database.execute_sql(f"""
            INSERT INTO llm_calls (request_id, provider, model, status)
            VALUES ({cascade_request_id}, 'openrouter', 'qwen/qwen3-max', 'ok')
        """)

        # Count LLM calls before delete
        result = db.fetchone("SELECT COUNT(*) FROM llm_calls")
        llm_before_delete = result[0]

        # Delete the request
        db._database.execute_sql(f"DELETE FROM requests WHERE id = {cascade_request_id}")

        # Count LLM calls after delete
        result = db.fetchone("SELECT COUNT(*) FROM llm_calls")
        llm_after_delete = result[0]

        if llm_after_delete == llm_before_delete - 1:
            print("-- CASCADE DELETE works (LLM call deleted with request)")
        else:
            print(f"FAIL: CASCADE DELETE failed: {llm_before_delete} -> {llm_after_delete}")
            pytest.fail("CASCADE DELETE failed to remove LLM call")

        print("\n" + "=" * 70)
        print("ALL PHASE 2 TESTS PASSED")
        print("=" * 70)
        print("\nSchema Improvements:")
        print("  - LLMCall.request is now NOT NULL")
        print("  - URL requests must have normalized_url")
        print("  - Forward requests must have fwd_from_chat_id and fwd_from_msg_id")
        print("  - CASCADE DELETE prevents orphaned LLM calls")

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        success = test_phase2_migration()
        sys.exit(0 if success else 1)
    except Exception:
        logger.exception("Test failed with exception")
        sys.exit(1)
