#!/usr/bin/env python3
"""Test script to verify Phase 2 schema improvements."""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

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
    """Test Phase 2 schema constraint improvements."""
    print("=" * 70)
    print("Testing Phase 2: Schema Integrity Improvements")
    print("=" * 70)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print(f"\n✓ Using temporary database: {db_path}")

        # Step 1: Create base schema + Phase 1 indexes (but NOT Phase 2 yet)
        print("\n[1] Creating base schema and applying Phase 1...")
        db = Database(path=db_path)
        db.migrate()

        runner = MigrationRunner(db)

        # Only apply Phase 1 (001_add_performance_indexes)
        pending = runner.get_pending_migrations()
        phase1_migration = [m for m in pending if "001_" in m.name]
        if phase1_migration:
            runner.run_migration(phase1_migration[0])
        print("✓ Base schema and Phase 1 completed (Phase 2 not yet applied)")

        # Step 2: Insert test data (including an orphaned LLM call)
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
            normalized_url="https://example.com",
        )

        # Insert a valid LLM call using ORM
        llm_call = LLMCall.create(
            request=request, provider="openrouter", model="gpt-4", status="ok"
        )
        assert llm_call.id is not None

        # Insert an orphaned LLM call (NULL request_id) using raw SQL
        db._database.execute_sql("""
            INSERT INTO llm_calls (request_id, provider, model, status)
            VALUES (NULL, 'openrouter', 'gpt-4', 'orphaned')
        """)

        # Count LLM calls before migration
        result = db.fetchone("SELECT COUNT(*) FROM llm_calls")
        llm_calls_before = result[0]
        print(f"✓ Test data created: {llm_calls_before} LLM calls (1 valid, 1 orphaned)")

        # Step 3: Apply Phase 2 migration (002_add_schema_constraints)
        print("\n[3] Applying Phase 2 migration...")
        pending = runner.get_pending_migrations()
        phase2_migration = [m for m in pending if "002_" in m.name]
        if not phase2_migration:
            print("⚠ No Phase 2 migration found!")
            return False
        runner.run_migration(phase2_migration[0])
        print("✓ Applied Phase 2 migration")

        # Step 4: Verify orphaned LLM calls were cleaned up
        print("\n[4] Verifying orphaned LLM calls cleanup...")
        result = db.fetchone("SELECT COUNT(*) FROM llm_calls")
        llm_calls_after = result[0]

        if llm_calls_after == llm_calls_before - 1:
            print(f"✓ Orphaned LLM call removed: {llm_calls_before} → {llm_calls_after}")
        else:
            print(f"✗ Expected {llm_calls_before - 1} LLM calls, found {llm_calls_after}")
            return False

        # Step 5: Test NOT NULL constraint on LLMCall.request
        print("\n[5] Testing NOT NULL constraint on LLMCall.request...")
        try:
            db._database.execute_sql("""
                INSERT INTO llm_calls (request_id, provider, model, status)
                VALUES (NULL, 'openrouter', 'gpt-4', 'should-fail')
            """)
            print("✗ NOT NULL constraint NOT enforced (insert succeeded when it should fail)")
            return False
        except Exception as e:
            if "NOT NULL" in str(e) or "constraint" in str(e).lower():
                print("✓ NOT NULL constraint enforced (insert correctly rejected)")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 6: Test CHECK constraint for URL requests
        print("\n[6] Testing CHECK constraint for URL requests...")
        try:
            # Try to insert URL request without normalized_url
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, created_at)
                VALUES ('url', 'ok', 'test-invalid-url', 123456789, datetime('now'))
            """)
            print("✗ CHECK constraint NOT enforced for URL requests")
            return False
        except Exception as e:
            if "validation" in str(e).lower() or "abort" in str(e).lower():
                print("✓ CHECK constraint enforced for URL requests")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 7: Test CHECK constraint for forward requests
        print("\n[7] Testing CHECK constraint for forward requests...")
        try:
            # Try to insert forward request without fwd_from_chat_id
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, fwd_from_msg_id, created_at)
                VALUES ('forward', 'ok', 'test-invalid-forward', 123456789, 999, datetime('now'))
            """)
            print("✗ CHECK constraint NOT enforced for forward requests")
            return False
        except Exception as e:
            if "validation" in str(e).lower() or "abort" in str(e).lower():
                print("✓ CHECK constraint enforced for forward requests")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 8: Verify valid requests still work
        print("\n[8] Verifying valid requests still work...")

        # Valid URL request
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, normalized_url, created_at)
            VALUES ('url', 'ok', 'test-valid-url', 123456789, 'https://valid.com', datetime('now'))
        """)

        # Valid forward request
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, fwd_from_chat_id, fwd_from_msg_id, created_at)
            VALUES ('forward', 'ok', 'test-valid-forward', 123456789, -100123456789, 999, datetime('now'))
        """)

        result = db.fetchone(
            "SELECT COUNT(*) FROM requests WHERE correlation_id LIKE 'test-valid-%'"
        )
        valid_count = result[0]

        if valid_count == 2:
            print("✓ Valid requests accepted (2 created)")
        else:
            print(f"✗ Expected 2 valid requests, found {valid_count}")
            return False

        # Step 9: Verify foreign key CASCADE on LLMCall
        print("\n[9] Verifying CASCADE on DELETE for LLMCall.request...")

        # Create a request with an LLM call
        db._database.execute_sql("""
            INSERT INTO requests (type, status, correlation_id, user_id, normalized_url, created_at)
            VALUES ('url', 'ok', 'test-cascade', 123456789, 'https://cascade.com', datetime('now'))
        """)

        result = db.fetchone("SELECT id FROM requests WHERE correlation_id = 'test-cascade'")
        cascade_request_id = result[0]

        db._database.execute_sql(f"""
            INSERT INTO llm_calls (request_id, provider, model, status)
            VALUES ({cascade_request_id}, 'openrouter', 'gpt-4', 'ok')
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
            print("✓ CASCADE DELETE works (LLM call deleted with request)")
        else:
            print(f"✗ CASCADE DELETE failed: {llm_before_delete} → {llm_after_delete}")
            return False

        print("\n" + "=" * 70)
        print("✓ ALL PHASE 2 TESTS PASSED!")
        print("=" * 70)
        print("\nSchema Improvements:")
        print("  ✓ LLMCall.request is now NOT NULL")
        print("  ✓ Orphaned LLM calls cleaned up")
        print("  ✓ URL requests must have normalized_url")
        print("  ✓ Forward requests must have fwd_from_chat_id and fwd_from_msg_id")
        print("  ✓ CASCADE DELETE prevents orphaned LLM calls")
        return True

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
