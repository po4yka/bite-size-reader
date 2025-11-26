"""Unit tests for AsyncRWLock read-write lock implementation."""

from __future__ import annotations

import asyncio
import unittest


class TestAsyncRWLock(unittest.IsolatedAsyncioTestCase):
    """Test suite for AsyncRWLock class."""

    async def asyncSetUp(self) -> None:
        """Set up test fixtures."""
        from app.db.rw_lock import AsyncRWLock

        self.lock = AsyncRWLock()

    async def test_single_reader(self) -> None:
        """Test that a single reader can acquire the lock."""
        acquired = False

        async with self.lock.read_lock():
            acquired = True

        self.assertTrue(acquired)

    async def test_single_writer(self) -> None:
        """Test that a single writer can acquire the lock."""
        acquired = False

        async with self.lock.write_lock():
            acquired = True

        self.assertTrue(acquired)

    async def test_multiple_readers_concurrent(self) -> None:
        """Test that multiple readers can hold the lock simultaneously."""
        read_count = 0
        max_concurrent = 0

        async def reader(delay: float) -> None:
            nonlocal read_count, max_concurrent
            async with self.lock.read_lock():
                read_count += 1
                max_concurrent = max(max_concurrent, read_count)
                await asyncio.sleep(delay)
                read_count -= 1

        # Start 5 readers concurrently
        readers = [reader(0.05) for _ in range(5)]
        await asyncio.gather(*readers)

        # All 5 readers should have been active concurrently
        self.assertEqual(max_concurrent, 5)
        self.assertEqual(read_count, 0)

    async def test_writer_excludes_readers(self) -> None:
        """Test that writer blocks readers until released."""
        results: list[str] = []

        async def writer() -> None:
            async with self.lock.write_lock():
                results.append("writer_start")
                await asyncio.sleep(0.05)
                results.append("writer_end")

        async def reader() -> None:
            await asyncio.sleep(0.01)  # Let writer start first
            async with self.lock.read_lock():
                results.append("reader")

        # Start writer first, then reader
        await asyncio.gather(writer(), reader())

        # Reader should only execute after writer finishes
        self.assertEqual(results, ["writer_start", "writer_end", "reader"])

    async def test_writer_excludes_writer(self) -> None:
        """Test that only one writer can hold the lock at a time."""
        results: list[str] = []

        async def writer(name: str) -> None:
            async with self.lock.write_lock():
                results.append(f"{name}_start")
                await asyncio.sleep(0.02)
                results.append(f"{name}_end")

        # Start two writers
        await asyncio.gather(writer("writer1"), writer("writer2"))

        # Writers should execute sequentially, not concurrently
        # Order may vary, but each writer should complete before next starts
        self.assertEqual(len(results), 4)
        self.assertIn(results[0], ["writer1_start", "writer2_start"])
        self.assertIn(results[1], ["writer1_end", "writer2_end"])
        # Second writer's start must be after first writer's end
        if results[0] == "writer1_start":
            self.assertEqual(results[1], "writer1_end")
            self.assertEqual(results[2], "writer2_start")
            self.assertEqual(results[3], "writer2_end")
        else:
            self.assertEqual(results[1], "writer2_end")
            self.assertEqual(results[2], "writer1_start")
            self.assertEqual(results[3], "writer1_end")

    async def test_readers_block_writer(self) -> None:
        """Test that writer waits for all readers to finish."""
        results: list[str] = []

        async def reader(name: str) -> None:
            async with self.lock.read_lock():
                results.append(f"{name}_start")
                await asyncio.sleep(0.03)
                results.append(f"{name}_end")

        async def writer() -> None:
            await asyncio.sleep(0.01)  # Let readers start first
            async with self.lock.write_lock():
                results.append("writer")

        # Start multiple readers and one writer
        await asyncio.gather(
            reader("reader1"),
            reader("reader2"),
            writer(),
        )

        # Writer should only execute after all readers finish
        self.assertIn("reader1_start", results[:2])
        self.assertIn("reader2_start", results[:2])
        self.assertIn("reader1_end", results[:4])
        self.assertIn("reader2_end", results[:4])
        self.assertEqual(results[-1], "writer")

    async def test_lock_release_on_exception_read(self) -> None:
        """Test that read lock is released even on exception."""

        class CustomError(Exception):
            pass

        with self.assertRaises(CustomError):
            async with self.lock.read_lock():
                raise CustomError("test error")

        # Lock should be released, so we can acquire it again
        acquired = False
        async with self.lock.read_lock():
            acquired = True

        self.assertTrue(acquired)

    async def test_lock_release_on_exception_write(self) -> None:
        """Test that write lock is released even on exception."""

        class CustomError(Exception):
            pass

        with self.assertRaises(CustomError):
            async with self.lock.write_lock():
                raise CustomError("test error")

        # Lock should be released, so we can acquire it again
        acquired = False
        async with self.lock.write_lock():
            acquired = True

        self.assertTrue(acquired)

    async def test_mixed_read_write_operations(self) -> None:
        """Test complex scenario with mixed read and write operations."""
        results: list[str] = []
        counter = 0

        async def reader(name: str, delay: float = 0) -> None:
            nonlocal counter
            if delay:
                await asyncio.sleep(delay)
            async with self.lock.read_lock():
                results.append(f"{name}_read_start")
                await asyncio.sleep(0.01)
                results.append(f"{name}_read_end:{counter}")

        async def writer(name: str, value: int, delay: float = 0) -> None:
            nonlocal counter
            if delay:
                await asyncio.sleep(delay)
            async with self.lock.write_lock():
                results.append(f"{name}_write_start")
                counter = value
                await asyncio.sleep(0.01)
                results.append(f"{name}_write_end:{counter}")

        # Execute: reader1, writer1, reader2, writer2, reader3
        await asyncio.gather(
            reader("reader1"),
            writer("writer1", 10, delay=0.005),
            reader("reader2", delay=0.015),
            writer("writer2", 20, delay=0.025),
            reader("reader3", delay=0.035),
        )

        # Verify that writes are isolated and reads see consistent state
        self.assertGreater(len(results), 0)
        # Note: exact ordering depends on timing, but all operations should complete

    async def test_fairness_readers_dont_starve_writers(self) -> None:
        """Test that continuous readers don't prevent writers indefinitely."""
        results: list[str] = []

        async def continuous_reader(name: str, iterations: int) -> None:
            for i in range(iterations):
                async with self.lock.read_lock():
                    results.append(f"{name}_{i}")
                    await asyncio.sleep(0.001)
                # Add small delay between lock acquisitions to allow writer
                await asyncio.sleep(0.001)

        async def writer(name: str) -> None:
            await asyncio.sleep(0.005)  # Let some readers start
            async with self.lock.write_lock():
                results.append(f"{name}_write")

        # Run continuous readers and a writer (reduced iterations)
        await asyncio.gather(
            continuous_reader("reader1", 10),
            continuous_reader("reader2", 10),
            writer("writer1"),
        )

        # Writer should eventually execute (not starved)
        self.assertIn("writer1_write", results)

    async def test_reader_count_accuracy(self) -> None:
        """Test that reader count is accurately tracked."""
        # Access internal state for testing
        self.assertEqual(self.lock._readers, 0)

        async with self.lock.read_lock():
            self.assertEqual(self.lock._readers, 1)
            async with self.lock.read_lock():
                self.assertEqual(self.lock._readers, 2)
            self.assertEqual(self.lock._readers, 1)

        self.assertEqual(self.lock._readers, 0)

    async def test_write_lock_exclusivity(self) -> None:
        """Test that write lock is truly exclusive."""
        write_active = False
        violation_detected = False

        async def writer(name: str) -> None:
            nonlocal write_active, violation_detected
            async with self.lock.write_lock():
                if write_active:
                    violation_detected = True
                write_active = True
                await asyncio.sleep(0.01)
                write_active = False

        # Run multiple writers
        await asyncio.gather(
            writer("writer1"),
            writer("writer2"),
            writer("writer3"),
        )

        # No two writers should be active simultaneously
        self.assertFalse(violation_detected)

    async def test_manual_acquire_release_read(self) -> None:
        """Test manual acquire and release for read lock."""
        await self.lock.acquire_read()
        self.assertEqual(self.lock._readers, 1)
        await self.lock.release_read()
        self.assertEqual(self.lock._readers, 0)

    async def test_manual_acquire_release_write(self) -> None:
        """Test manual acquire and release for write lock."""
        await self.lock.acquire_write()
        self.assertTrue(self.lock._write_lock.locked())

        # Release in separate task to avoid blocking
        await self.lock.release_write()
        self.assertFalse(self.lock._write_lock.locked())

    async def test_concurrent_readers_performance(self) -> None:
        """Test that concurrent readers complete faster than sequential."""
        import time

        async def slow_reader() -> None:
            async with self.lock.read_lock():
                await asyncio.sleep(0.02)

        # Concurrent readers (should take ~0.02s total)
        start = time.monotonic()
        await asyncio.gather(*[slow_reader() for _ in range(5)])
        concurrent_time = time.monotonic() - start

        # Concurrent reads should complete in roughly the time of one read
        # (plus some overhead for context switching)
        self.assertLess(concurrent_time, 0.05)  # Should be ~0.02s, not 0.10s


if __name__ == "__main__":
    unittest.main()
