"""Tests for DB thread operation completion under parent coroutine cancellation.

When ``_safe_db_operation`` uses ``asyncio.wait_for(asyncio.to_thread(...))``,
a timeout cancels the *awaiting* coroutine but the underlying OS thread keeps
running as a zombie.  Wrapping ``asyncio.to_thread`` in ``asyncio.shield()``
ensures the thread operation completes and its result is properly collected,
even when the parent coroutine is cancelled.

These tests verify:
1. Thread operations complete their side effects even after timeout/cancellation.
2. The caller correctly receives ``TimeoutError`` when the deadline expires.
3. No zombie threads are left behind (the shielded future settles).
"""

from __future__ import annotations

import asyncio
import threading
import time
import unittest
from typing import Any

from app.db.session import DatabaseSessionManager


def _make_session_manager() -> DatabaseSessionManager:
    """Create a minimal in-memory DatabaseSessionManager for testing."""
    return DatabaseSessionManager(
        path=":memory:",
        operation_timeout=10.0,
        max_retries=0,
    )


class TestSafeDbOperationCancellation(unittest.IsolatedAsyncioTestCase):
    """Verify _safe_db_operation behavior when the parent task is cancelled."""

    def setUp(self) -> None:
        self.manager = _make_session_manager()

    async def test_thread_op_completes_after_timeout(self) -> None:
        """Thread operation finishes its side effects even after wait_for timeout.

        A slow blocking callable is submitted via _safe_db_operation with a very
        short timeout.  The operation records that it started and completed via
        a threading.Event.  After the TimeoutError, we wait briefly for the
        thread to finish and verify the side effect landed.
        """
        started = threading.Event()
        completed = threading.Event()

        def slow_operation() -> str:
            started.set()
            time.sleep(0.3)
            completed.set()
            return "done"

        with self.assertRaises(TimeoutError):
            await self.manager._safe_db_operation(
                slow_operation,
                timeout=0.05,
                operation_name="test_slow_op",
            )

        # The thread was started before the timeout fired.
        self.assertTrue(started.is_set(), "thread operation should have started")

        # Wait for the thread to finish (it will, because threads are not killed).
        completed.wait(timeout=2.0)
        self.assertTrue(
            completed.is_set(),
            "thread operation should complete even after parent cancellation",
        )

    async def test_successful_op_returns_result(self) -> None:
        """Non-cancelled operations return their result normally."""

        def fast_operation() -> int:
            return 42

        result = await self.manager._safe_db_operation(
            fast_operation,
            timeout=5.0,
            operation_name="test_fast_op",
        )
        self.assertEqual(result, 42)

    async def test_read_only_thread_completes_after_cancellation(self) -> None:
        """read_only=True path also completes its thread after cancellation."""
        completed = threading.Event()

        def slow_read() -> str:
            time.sleep(0.3)
            completed.set()
            return "read_done"

        with self.assertRaises(TimeoutError):
            await self.manager._safe_db_operation(
                slow_read,
                timeout=0.05,
                operation_name="test_slow_read",
                read_only=True,
            )

        completed.wait(timeout=2.0)
        self.assertTrue(
            completed.is_set(),
            "read-only thread operation should complete after cancellation",
        )

    async def test_external_task_cancel_does_not_abandon_thread(self) -> None:
        """When an external caller cancels the task, the thread still finishes.

        This simulates the scenario where a Telegram handler or an outer
        ``asyncio.wait_for`` cancels the coroutine that called
        ``_safe_db_operation``.
        """
        started = threading.Event()
        completed = threading.Event()
        result_holder: list[str] = []

        def blocking_write() -> str:
            started.set()
            time.sleep(0.3)
            result_holder.append("written")
            completed.set()
            return "ok"

        async def run_db_op() -> Any:
            return await self.manager._safe_db_operation(
                blocking_write,
                timeout=10.0,  # long timeout -- won't fire
                operation_name="test_external_cancel",
            )

        task = asyncio.create_task(run_db_op())

        # Wait until the thread has started, then cancel the task.
        await asyncio.to_thread(started.wait, 2.0)
        self.assertTrue(started.is_set())
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        # Thread should still complete.
        completed.wait(timeout=2.0)
        self.assertTrue(
            completed.is_set(),
            "thread should finish despite task cancellation",
        )
        self.assertEqual(result_holder, ["written"])

    async def test_shielded_future_settles_no_zombie(self) -> None:
        """After timeout, any shielded inner future must eventually settle.

        If ``asyncio.shield`` is used properly, the inner future resolves on
        its own.  This test ensures no unresolved futures remain after the
        thread finishes.
        """
        settled = asyncio.Event()

        async def _shielded_to_thread(fn: Any) -> Any:
            """Emulate the shielded pattern we want in _safe_db_operation."""
            inner = asyncio.ensure_future(asyncio.to_thread(fn))
            try:
                return await asyncio.shield(inner)
            except asyncio.CancelledError:
                # The shield was cancelled but the inner future should continue.
                # We attach a callback to track settlement.
                inner.add_done_callback(lambda _: settled.set())
                raise

        def slow_fn() -> str:
            time.sleep(0.2)
            return "settled"

        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(_shielded_to_thread(slow_fn), timeout=0.05)

        # The inner future should settle within a reasonable time.
        await asyncio.wait_for(settled.wait(), timeout=2.0)
        self.assertTrue(settled.is_set(), "shielded future should settle (no zombie)")


class TestSafeDbTransactionCancellation(unittest.IsolatedAsyncioTestCase):
    """Verify _safe_db_transaction behavior under cancellation."""

    def setUp(self) -> None:
        self.manager = _make_session_manager()

    async def test_transaction_thread_completes_after_timeout(self) -> None:
        """Transaction thread operations also complete after timeout."""
        completed = threading.Event()

        def slow_transaction() -> str:
            time.sleep(0.3)
            completed.set()
            return "committed"

        with self.assertRaises(TimeoutError):
            await self.manager._safe_db_transaction(
                slow_transaction,
                timeout=0.05,
                operation_name="test_slow_txn",
            )

        completed.wait(timeout=2.0)
        self.assertTrue(
            completed.is_set(),
            "transaction thread should complete after timeout",
        )


if __name__ == "__main__":
    unittest.main()
