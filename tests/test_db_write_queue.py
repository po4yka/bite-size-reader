"""Tests for DbWriteQueue background write queue."""

from __future__ import annotations

import asyncio
import unittest


class TestDbWriteQueue(unittest.IsolatedAsyncioTestCase):
    """Test suite for DbWriteQueue class."""

    async def _make_queue(self, maxsize: int = 256):
        """Create and start a DbWriteQueue, returning it."""
        from app.db.write_queue import DbWriteQueue

        q = DbWriteQueue(maxsize=maxsize)
        q.start()
        return q

    # ------------------------------------------------------------------
    # Core behaviour
    # ------------------------------------------------------------------

    async def test_processes_items_in_order(self) -> None:
        """Enqueued operations execute in FIFO order."""
        q = await self._make_queue()
        results: list[int] = []

        for i in range(5):

            async def _write(val: int = i) -> None:
                results.append(val)

            await q.enqueue(_write, operation_name=f"write_{i}", correlation_id=str(i))

        await q.stop(timeout=5.0)
        self.assertEqual(results, [0, 1, 2, 3, 4])

    async def test_continues_after_item_error(self) -> None:
        """A failing operation must not crash the worker; later items still run."""
        q = await self._make_queue()
        results: list[str] = []

        async def _good(label: str) -> None:
            results.append(label)

        async def _bad() -> None:
            msg = "deliberate test failure"
            raise RuntimeError(msg)

        await q.enqueue(lambda: _good("first"), operation_name="good1")
        await q.enqueue(_bad, operation_name="bad")
        await q.enqueue(lambda: _good("third"), operation_name="good2")

        await q.stop(timeout=5.0)
        self.assertEqual(results, ["first", "third"])

    async def test_drains_on_graceful_shutdown(self) -> None:
        """Items enqueued before stop() are drained before the worker exits."""
        q = await self._make_queue()
        results: list[int] = []
        barrier = asyncio.Event()

        async def _blocking_write() -> None:
            # Hold the worker busy until we release it.
            await barrier.wait()
            results.append(0)

        async def _quick_write(val: int) -> None:
            results.append(val)

        # Enqueue a blocking item so that items 1-3 pile up behind it.
        await q.enqueue(_blocking_write, operation_name="blocking")
        for i in range(1, 4):

            async def _w(v: int = i) -> None:
                results.append(v)

            await q.enqueue(_w, operation_name=f"write_{i}")

        # Release the blocking write and immediately request shutdown.
        barrier.set()
        await q.stop(timeout=5.0)

        self.assertEqual(results, [0, 1, 2, 3])

    async def test_backpressure_on_full_queue(self) -> None:
        """enqueue() blocks when the queue is full, then succeeds once space opens."""
        q = await self._make_queue(maxsize=2)
        results: list[int] = []
        hold = asyncio.Event()
        worker_entered = asyncio.Event()

        async def _hold_write() -> None:
            worker_entered.set()
            await hold.wait()
            results.append(0)

        async def _quick(val: int) -> None:
            results.append(val)

        # Enqueue the blocking item and wait for the worker to pick it up.
        await q.enqueue(_hold_write, operation_name="hold")
        await worker_entered.wait()

        # Now the worker is blocked on _hold_write.  The queue is empty.
        # Fill both queue slots so the next enqueue must block.
        await q.enqueue(lambda: _quick(1), operation_name="q1")
        await q.enqueue(lambda: _quick(2), operation_name="q2")

        # Next enqueue must block because maxsize=2 and queue is full.
        enqueue_done = asyncio.Event()

        async def _enqueue_overflow() -> None:
            await q.enqueue(lambda: _quick(3), operation_name="q3")
            enqueue_done.set()

        task = asyncio.create_task(_enqueue_overflow())

        # Give the event loop a few cycles -- enqueue should NOT have completed.
        await asyncio.sleep(0.05)
        self.assertFalse(enqueue_done.is_set(), "enqueue should block on a full queue")

        # Release the held write so the worker drains and makes room.
        hold.set()
        await asyncio.wait_for(enqueue_done.wait(), timeout=5.0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await q.stop(timeout=5.0)
        self.assertIn(3, results)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    async def test_stop_is_idempotent(self) -> None:
        """Calling stop() twice must not raise."""
        q = await self._make_queue()
        await q.stop(timeout=2.0)
        await q.stop(timeout=2.0)  # second call is a no-op

    async def test_start_is_idempotent(self) -> None:
        """Calling start() when already running logs a warning but does not crash."""
        q = await self._make_queue()
        q.start()  # second start -- should be harmless
        await q.stop(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
