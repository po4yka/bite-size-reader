#!/usr/bin/env python3
"""Test script to verify Phase 3 performance improvements."""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.cli.migrations.migration_runner import MigrationRunner
from app.db.batch_operations import BatchOperations
from app.db.database import Database
from app.db.health_check import DatabaseHealthCheck
from app.db.query_cache import QueryCache

logging.basicConfig(
    level=logging.WARNING,  # Reduce noise
    format="%(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_phase3() -> bool:
    """Test Phase 3 performance improvements."""
    print("=" * 70)
    print("Testing Phase 3: Performance Improvements")
    print("=" * 70)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        print(f"\n✓ Using temporary database: {db_path}")

        # Step 1: Apply all migrations (Phase 1 + Phase 2)
        print("\n[1] Applying all migrations...")
        db = Database(path=db_path)
        db.migrate()

        runner = MigrationRunner(db)
        count = runner.run_pending()
        print(f"✓ Applied {count} migration(s)")

        # Step 2: Create test data
        print("\n[2] Creating test data...")
        from app.db.models import LLMCall, Request, User

        user = User.create(telegram_user_id=123456789, username="testuser", is_owner=True)

        requests = []
        for i in range(5):
            request = Request.create(
                type="url",
                status="ok",
                correlation_id=f"test-{i}",
                user_id=user.telegram_user_id,
                normalized_url=f"https://example.com/{i}",
            )
            requests.append(request)

        print(f"✓ Created {len(requests)} test requests")

        # Step 3: Test Query Cache
        print("\n[3] Testing query result caching...")
        cache = QueryCache(max_size=10)

        # Create cached function
        @cache.cache_query("test_query")
        def get_request_by_id(request_id: int) -> Request | None:
            return Request.get_or_none(Request.id == request_id)

        # First call - cache miss
        result1 = get_request_by_id(requests[0].id)
        stats1 = cache.get_stats()

        # Second call - cache hit
        result2 = get_request_by_id(requests[0].id)
        stats2 = cache.get_stats()

        if result1 and result2 and result1.id == result2.id:
            print("✓ Query cache working (same result)")
        else:
            print("✗ Query cache failed (different results)")
            return False

        # Cache should have hits now
        if stats2["hits"] > stats1["hits"]:
            print("✓ Cache hit detected")
        else:
            print("✗ Cache hit not detected")
            return False

        # Test cache invalidation
        cache.invalidate("test_query")
        stats3 = cache.get_stats()
        if stats3["invalidations"] > 0:
            print("✓ Cache invalidation working")
        else:
            print("✗ Cache invalidation failed")
            return False

        # Step 4: Test Batch Operations
        print("\n[4] Testing batch operations...")
        batch = BatchOperations(db._database)

        # Test batch LLM call insertion
        llm_call_data = [
            {
                "request_id": requests[i].id,
                "provider": "openrouter",
                "model": "gpt-4",
                "status": "ok",
                "latency_ms": 1000 + i * 100,
            }
            for i in range(3)
        ]

        llm_call_ids = batch.insert_llm_calls_batch(llm_call_data)
        if len(llm_call_ids) == 3:
            print(f"✓ Batch insert created {len(llm_call_ids)} LLM calls")
        else:
            print(f"✗ Batch insert failed: expected 3, got {len(llm_call_ids)}")
            return False

        # Test batch status update
        status_updates = [
            (requests[0].id, "processing"),
            (requests[1].id, "processing"),
        ]
        updated_count = batch.update_request_statuses_batch(status_updates)
        if updated_count == 2:
            print(f"✓ Batch status update modified {updated_count} rows")
        else:
            print(f"✗ Batch status update failed: expected 2, got {updated_count}")
            return False

        # Test batch fetch
        request_ids = [r.id for r in requests[:3]]
        fetched_requests = batch.get_requests_by_ids_batch(request_ids)
        if len(fetched_requests) == 3:
            print(f"✓ Batch fetch retrieved {len(fetched_requests)} requests")
        else:
            print(f"✗ Batch fetch failed: expected 3, got {len(fetched_requests)}")
            return False

        # Step 5: Test Database Health Check
        print("\n[5] Testing database health check...")
        health = DatabaseHealthCheck(db._database, db_path)

        # Run comprehensive health check
        result = health.run_health_check()

        print(f"  Status: {result.status}")
        print(f"  Healthy: {result.healthy}")
        print(f"  Overall Score: {result.overall_score:.2f}")

        # Check specific health checks
        required_checks = [
            "connectivity",
            "foreign_keys",
            "indexes",
            "disk_space",
            "query_performance",
            "data_integrity",
            "wal_mode",
        ]

        all_checks_passed = True
        for check_name in required_checks:
            check_result = result.checks.get(check_name, {})
            is_healthy = check_result.get("healthy", False)
            message = check_result.get("message", "No message")

            if is_healthy:
                print(f"  ✓ {check_name}: {message}")
            else:
                print(f"  ✗ {check_name}: {check_result.get('error', message)}")
                all_checks_passed = False

        if not all_checks_passed:
            print("✗ Some health checks failed")
            return False

        print("✓ All health checks passed")

        # Get database stats
        stats = health.get_database_stats()
        print("\nDatabase Stats:")
        print(f"  Requests: {stats.get('requests', 0)}")
        print(f"  Summaries: {stats.get('summaries', 0)}")
        print(f"  LLM Calls: {stats.get('llm_calls', 0)}")
        if "db_size_mb" in stats:
            print(f"  DB Size: {stats['db_size_mb']} MB")

        # Step 6: Test Batch Delete (CASCADE should work)
        print("\n[6] Testing batch delete with CASCADE...")

        # Create a request with related records
        test_request = Request.create(
            type="url",
            status="ok",
            correlation_id="test-cascade-delete",
            user_id=user.telegram_user_id,
            normalized_url="https://cascade-test.com",
        )

        test_llm_call = LLMCall.create(
            request=test_request, provider="openrouter", model="gpt-4", status="ok"
        )
        assert test_llm_call.id is not None

        # Count LLM calls before delete
        llm_count_before = LLMCall.select().count()

        # Delete request (should CASCADE to LLM call)
        deleted = batch.delete_requests_batch([test_request.id])

        # Count LLM calls after delete
        llm_count_after = LLMCall.select().count()

        if deleted == 1 and llm_count_after == llm_count_before - 1:
            print("✓ Batch delete with CASCADE works")
        else:
            print("✗ Batch delete CASCADE failed")
            print(f"  Deleted requests: {deleted}")
            print(f"  LLM calls before: {llm_count_before}, after: {llm_count_after}")
            return False

        print("\n" + "=" * 70)
        print("✓ ALL PHASE 3 TESTS PASSED!")
        print("=" * 70)
        print("\nPerformance Improvements Verified:")
        print("  ✓ Query result caching (LRU with auto-invalidation)")
        print("  ✓ Batch insert operations (multiple rows in one transaction)")
        print("  ✓ Batch update operations (efficient status updates)")
        print("  ✓ Batch fetch operations (IN clause queries)")
        print("  ✓ Database health checks (7 checks)")
        print("  ✓ Comprehensive database statistics")
        return True

    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        success = test_phase3()
        sys.exit(0 if success else 1)
    except Exception:
        logger.exception("Test failed with exception")
        sys.exit(1)
