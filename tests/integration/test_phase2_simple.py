#!/usr/bin/env python3
"""Simplified test for Phase 2 schema improvements."""

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
    level=logging.WARNING,  # Reduce noise
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_phase2():
    """Test Phase 2 schema constraints."""
    print("=" * 70)
    print("Testing Phase 2: Schema Integrity Improvements")
    print("=" * 70)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print(f"\n✓ Using temporary database: {db_path}")

        # Step 1: Apply all migrations
        print("\n[1] Applying all migrations...")
        db = Database(path=db_path)
        db.migrate()

        runner = MigrationRunner(db)
        count = runner.run_pending()
        print(f"✓ Applied {count} migration(s)")

        # Step 2: Verify NOT NULL constraint on LLMCall.request
        print("\n[2] Testing NOT NULL constraint on LLMCall.request...")
        try:
            db._database.execute_sql("""
                INSERT INTO llm_calls (request_id, provider, model, status)
                VALUES (NULL, 'openrouter', 'gpt-4', 'should-fail')
            """)
            print("✗ NOT NULL constraint NOT enforced")
            return False
        except Exception as e:
            if "NOT NULL" in str(e):
                print("✓ NOT NULL constraint enforced")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 3: Create test user
        print("\n[3] Creating test user...")
        from app.db.models import User

        user = User.create(telegram_user_id=123456789, username="testuser", is_owner=True)
        print("✓ Test user created")

        # Step 4: Test CHECK constraint for URL requests
        print("\n[4] Testing CHECK constraint for URL requests...")
        try:
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, created_at, route_version)
                VALUES ('url', 'ok', 'test-no-url', 123456789, datetime('now'), 1)
            """)
            print("✗ CHECK constraint NOT enforced for URL requests")
            return False
        except Exception as e:
            if "validation" in str(e).lower():
                print("✓ CHECK constraint enforced for URL requests")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 5: Test CHECK constraint for forward requests
        print("\n[5] Testing CHECK constraint for forward requests...")
        try:
            db._database.execute_sql("""
                INSERT INTO requests (type, status, correlation_id, user_id, fwd_from_msg_id, created_at, route_version)
                VALUES ('forward', 'ok', 'test-no-chat', 123456789, 999, datetime('now'), 1)
            """)
            print("✗ CHECK constraint NOT enforced for forward requests")
            return False
        except Exception as e:
            if "validation" in str(e).lower():
                print("✓ CHECK constraint enforced for forward requests")
            else:
                print(f"✗ Unexpected error: {e}")
                return False

        # Step 6: Verify valid requests still work
        print("\n[6] Testing valid requests...")
        from app.db.models import LLMCall, Request

        # Valid URL request
        url_request = Request.create(
            type="url",
            status="ok",
            correlation_id="test-valid-url",
            user_id=user.telegram_user_id,
            normalized_url="https://example.com",
        )
        assert url_request.id is not None

        # Valid forward request
        fwd_request = Request.create(
            type="forward",
            status="ok",
            correlation_id="test-valid-forward",
            user_id=user.telegram_user_id,
            fwd_from_chat_id=-100123456789,
            fwd_from_msg_id=999,
        )
        assert fwd_request.id is not None

        print("✓ Valid requests accepted")

        # Step 7: Verify CASCADE DELETE
        print("\n[7] Testing CASCADE DELETE for LLMCall.request...")

        cascade_request = Request.create(
            type="url",
            status="ok",
            correlation_id="test-cascade",
            user_id=user.telegram_user_id,
            normalized_url="https://cascade.com",
        )

        cascade_llm = LLMCall.create(
            request=cascade_request, provider="openrouter", model="gpt-4", status="ok"
        )

        llm_id = cascade_llm.id

        # Delete the request
        cascade_request.delete_instance()

        # Verify LLM call was also deleted
        try:
            LLMCall.get_by_id(llm_id)
            print("✗ CASCADE DELETE failed (LLM call still exists)")
            return False
        except LLMCall.DoesNotExist:
            print("✓ CASCADE DELETE works (LLM call deleted with request)")

        print("\n" + "=" * 70)
        print("✓ ALL PHASE 2 TESTS PASSED!")
        print("=" * 70)
        print("\nSchema Improvements Verified:")
        print("  ✓ LLMCall.request is now NOT NULL")
        print("  ✓ URL requests must have normalized_url")
        print("  ✓ Forward requests must have fwd_from_chat_id and fwd_from_msg_id")
        print("  ✓ Valid requests work correctly")
        print("  ✓ CASCADE DELETE prevents orphaned LLM calls")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        success = test_phase2()
        sys.exit(0 if success else 1)
    except Exception:
        logger.exception("Test failed with exception")
        sys.exit(1)
