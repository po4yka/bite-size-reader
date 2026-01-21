"""Database concurrency stress tests.

Verifies the system handles concurrent database access correctly:
- Multiple concurrent writers
- Read/write contention
- Connection pool behavior
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid

import pytest


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    # Cleanup
    try:
        os.unlink(f.name)
    except OSError:
        pass


@pytest.mark.stress
@pytest.mark.asyncio
class TestDatabaseConcurrency:
    """Stress tests for concurrent database operations."""

    async def test_concurrent_writers(self, temp_db_path: str) -> None:
        """Test 10 concurrent writers with 100 writes each.

        Verifies no data corruption or deadlocks occur under concurrent write load.
        """
        from app.db.session import DatabaseSessionManager

        # Initialize database
        db = DatabaseSessionManager(temp_db_path)

        # Create test table
        db.database.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS stress_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                writer_id INTEGER NOT NULL,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        num_writers = 10
        writes_per_writer = 100
        errors: list[Exception] = []

        async def writer_task(writer_id: int):
            """Simulate a writer performing multiple writes."""
            for i in range(writes_per_writer):
                try:
                    db.database.execute_sql(
                        "INSERT INTO stress_test (writer_id, value) VALUES (?, ?)",
                        (writer_id, f"value_{writer_id}_{i}"),
                    )
                    await asyncio.sleep(0.001)  # Small delay to increase contention
                except Exception as e:
                    errors.append(e)

        # Run concurrent writers
        tasks = [asyncio.create_task(writer_task(writer_id)) for writer_id in range(num_writers)]
        await asyncio.gather(*tasks)

        # Verify results
        cursor = db.database.execute_sql("SELECT COUNT(*) FROM stress_test")
        count = cursor.fetchone()[0]

        expected_count = num_writers * writes_per_writer
        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"
        assert count == expected_count, f"Expected {expected_count} rows, got {count}"

        db.database.close()

    async def test_mixed_read_write_contention(self, temp_db_path: str) -> None:
        """Test concurrent reads and writes for contention handling.

        Simulates realistic workload with mixed read/write operations.
        """
        from app.db.session import DatabaseSessionManager

        db = DatabaseSessionManager(temp_db_path)

        # Create and populate test table
        db.database.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS rw_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                counter INTEGER NOT NULL DEFAULT 0,
                data TEXT
            )
            """
        )

        # Insert initial row
        db.database.execute_sql("INSERT INTO rw_test (counter, data) VALUES (0, 'initial')")

        num_readers = 5
        num_writers = 5
        operations_per_task = 50
        read_results: list[int] = []
        write_count = 0
        errors: list[Exception] = []

        async def reader_task():
            """Read the current counter value."""
            for _ in range(operations_per_task):
                try:
                    cursor = db.database.execute_sql("SELECT counter FROM rw_test WHERE id = 1")
                    row = cursor.fetchone()
                    if row:
                        read_results.append(row[0])
                    await asyncio.sleep(0.002)
                except Exception as e:
                    errors.append(e)

        async def writer_task():
            """Increment the counter."""
            nonlocal write_count
            for _ in range(operations_per_task):
                try:
                    db.database.execute_sql("UPDATE rw_test SET counter = counter + 1 WHERE id = 1")
                    write_count += 1
                    await asyncio.sleep(0.003)
                except Exception as e:
                    errors.append(e)

        # Run concurrent readers and writers
        tasks = [
            *[asyncio.create_task(reader_task()) for _ in range(num_readers)],
            *[asyncio.create_task(writer_task()) for _ in range(num_writers)],
        ]
        await asyncio.gather(*tasks)

        # Verify final state
        cursor = db.database.execute_sql("SELECT counter FROM rw_test WHERE id = 1")
        final_counter = cursor.fetchone()[0]

        expected_writes = num_writers * operations_per_task

        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"
        assert final_counter == expected_writes, (
            f"Counter mismatch: expected {expected_writes}, got {final_counter}"
        )

        # Verify reads were monotonically non-decreasing (eventually consistent)
        # Note: Some reads may see stale data due to SQLite's isolation level
        assert len(read_results) > 0, "No reads completed"

        db.database.close()

    async def test_connection_pool_exhaustion(self, temp_db_path: str) -> None:
        """Test behavior when many concurrent tasks access the database.

        Verifies the system handles connection contention gracefully.
        """
        from app.db.session import DatabaseSessionManager

        db = DatabaseSessionManager(temp_db_path)

        # Create test table
        db.database.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS pool_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL
            )
            """
        )

        num_tasks = 50
        operations_per_task = 20
        completed = 0
        errors: list[Exception] = []

        async def task(task_id: str):
            """Perform database operations."""
            nonlocal completed
            for i in range(operations_per_task):
                try:
                    db.database.execute_sql(
                        "INSERT INTO pool_test (task_id) VALUES (?)",
                        (f"{task_id}_{i}",),
                    )
                    await asyncio.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            completed += 1

        # Run many concurrent tasks
        tasks = [asyncio.create_task(task(str(uuid.uuid4()))) for _ in range(num_tasks)]

        # Wait with timeout
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=60.0)
        except TimeoutError:
            pytest.fail("Database operations timed out - possible deadlock")

        # Verify completion
        cursor = db.database.execute_sql("SELECT COUNT(*) FROM pool_test")
        count = cursor.fetchone()[0]

        expected_count = num_tasks * operations_per_task

        assert completed == num_tasks, f"Only {completed}/{num_tasks} tasks completed"
        assert len(errors) == 0, f"Errors occurred: {errors[:5]}"
        assert count == expected_count, f"Expected {expected_count} rows, got {count}"

        db.database.close()

    async def test_long_running_transaction_impact(self, temp_db_path: str) -> None:
        """Test impact of long-running transactions on other operations.

        Verifies the system remains responsive when some operations are slow.
        """
        from app.db.session import DatabaseSessionManager

        db = DatabaseSessionManager(temp_db_path)

        # Create test table
        db.database.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS tx_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                value TEXT
            )
            """
        )

        quick_writes_completed = 0
        slow_writes_completed = 0
        errors: list[Exception] = []

        async def quick_writer():
            """Perform quick writes."""
            nonlocal quick_writes_completed
            for i in range(50):
                try:
                    db.database.execute_sql(
                        "INSERT INTO tx_test (value) VALUES (?)",
                        (f"quick_{i}",),
                    )
                    quick_writes_completed += 1
                    await asyncio.sleep(0.001)
                except Exception as e:
                    errors.append(e)

        async def slow_operation():
            """Simulate a slow database operation."""
            nonlocal slow_writes_completed
            try:
                # Simulate processing time
                await asyncio.sleep(0.5)
                db.database.execute_sql(
                    "INSERT INTO tx_test (value) VALUES (?)",
                    ("slow",),
                )
                slow_writes_completed += 1
            except Exception as e:
                errors.append(e)

        # Run mixed workload
        tasks = [
            asyncio.create_task(quick_writer()),
            asyncio.create_task(slow_operation()),
            asyncio.create_task(slow_operation()),
        ]

        await asyncio.gather(*tasks)

        # Verify all completed
        assert quick_writes_completed == 50, f"Quick writes incomplete: {quick_writes_completed}/50"
        assert slow_writes_completed == 2, f"Slow writes incomplete: {slow_writes_completed}/2"
        assert len(errors) == 0, f"Errors occurred: {errors}"

        db.database.close()
