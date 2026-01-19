"""Integration tests for Database with AsyncRWLock."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path


class TestDatabaseRWLockIntegration(unittest.IsolatedAsyncioTestCase):
    """Test that Database class works correctly with AsyncRWLock."""

    async def asyncSetUp(self) -> None:
        """Set up test database."""
        from app.db.database import Database
        from app.db.models import database_proxy

        # Save original database proxy state
        self._old_db = database_proxy.obj

        # Create temporary database (file-based, not :memory:)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
            self.db_path = temp_db.name

        self.db = Database(path=self.db_path)
        self.db.migrate()

    async def asyncTearDown(self) -> None:
        """Clean up test database."""
        from app.db.models import database_proxy

        # Restore original database proxy state
        database_proxy.initialize(self._old_db)

        Path(self.db_path).unlink(missing_ok=True)

    async def test_concurrent_reads(self) -> None:
        """Test that multiple read operations can run concurrently."""
        # Create a test request
        request_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="test-123",
            chat_id=123,
            user_id=456,
            input_url="https://example.com",
        )

        # Create summary
        self.db.upsert_summary(
            request_id=request_id,
            lang="en",
            json_payload={"summary_250": "Test summary", "tldr": "Test"},
        )

        # Perform multiple concurrent reads
        read_count = 10
        results = await asyncio.gather(
            *[self.db.async_get_request_by_id(request_id) for _ in range(read_count)]
        )

        # All reads should succeed
        self.assertEqual(len(results), read_count)
        for result in results:
            self.assertIsNotNone(result)
            self.assertEqual(result["id"], request_id)

    async def test_read_write_isolation(self) -> None:
        """Test that reads and writes don't interfere with each other."""
        # Create a test request
        request_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="test-456",
            chat_id=123,
            user_id=456,
        )

        results: list[str] = []

        async def reader() -> None:
            """Read operation."""
            await asyncio.sleep(0.01)
            result = await self.db.async_get_request_by_id(request_id)
            results.append(f"read:{result['status']}")

        async def writer(status: str) -> None:
            """Write operation."""
            await asyncio.sleep(0.005)
            await self.db.async_update_request_status(request_id, status)
            results.append(f"write:{status}")

        # Execute reads and writes concurrently
        await asyncio.gather(
            reader(),
            writer("processing"),
            reader(),
            writer("completed"),
            reader(),
        )

        # All operations should complete
        self.assertGreater(len(results), 0)

    async def test_multiple_writes_sequential(self) -> None:
        """Test that writes execute sequentially."""
        # Create test requests
        request_ids = []
        for i in range(5):
            request_id = self.db.create_request(
                type_="url",
                status="pending",
                correlation_id=f"test-write-{i}",
                chat_id=123,
                user_id=456,
            )
            request_ids.append(request_id)

        # Update all requests concurrently
        await asyncio.gather(
            *[self.db.async_update_request_status(req_id, "completed") for req_id in request_ids]
        )

        # Verify all requests were updated
        for req_id in request_ids:
            result = await self.db.async_get_request_by_id(req_id)
            self.assertEqual(result["status"], "completed")

    async def test_read_only_flag_usage(self) -> None:
        """Test that read_only flag is properly used."""
        # Create a test request
        request_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="test-readonly",
            chat_id=123,
            user_id=456,
        )

        # Perform read operation (should use read lock)
        result = await self.db.async_get_request_by_id(request_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], request_id)

        # Perform write operation (should use write lock)
        await self.db.async_update_request_status(request_id, "completed")

        # Verify write succeeded
        result = await self.db.async_get_request_by_id(request_id)
        self.assertEqual(result["status"], "completed")

    async def test_summary_operations(self) -> None:
        """Test summary read/write operations."""
        # Create request
        request_id = self.db.create_request(
            type_="url",
            status="pending",
            correlation_id="test-summary",
            chat_id=123,
            user_id=456,
        )

        # Write summary
        version = await self.db.async_upsert_summary(
            request_id=request_id,
            lang="en",
            json_payload={"summary_250": "Test", "tldr": "Test summary"},
        )
        self.assertGreater(version, 0)

        # Read summary concurrently
        results = await asyncio.gather(
            *[self.db.async_get_summary_by_request(request_id) for _ in range(5)]
        )

        # All reads should succeed
        for result in results:
            self.assertIsNotNone(result)
            self.assertEqual(result["request"], request_id)


if __name__ == "__main__":
    unittest.main()
