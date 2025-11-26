"""Async read-write lock for database operations.

This module provides an AsyncRWLock implementation that allows multiple concurrent
readers OR one exclusive writer, improving database performance for read-heavy workloads.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class AsyncRWLock:
    """Async read-write lock allowing multiple readers OR one writer.

    This lock implements a reader-writer pattern where:
    - Multiple readers can acquire the lock simultaneously
    - Only one writer can hold the lock at a time
    - Writers have priority to prevent writer starvation

    Example:
        lock = AsyncRWLock()

        # For read operations
        async with lock.read_lock():
            data = await db.query("SELECT ...")

        # For write operations
        async with lock.write_lock():
            await db.execute("INSERT INTO ...")
    """

    def __init__(self) -> None:
        """Initialize the read-write lock."""
        # Number of active readers
        self._readers: int = 0

        # Lock for protecting reader count modifications
        self._reader_lock: asyncio.Lock = asyncio.Lock()

        # Lock for exclusive write access
        self._write_lock: asyncio.Lock = asyncio.Lock()

        # Condition to notify waiting writers when readers finish
        self._no_readers: asyncio.Condition = asyncio.Condition(self._reader_lock)

        # Event to signal when write lock is available
        self._write_available: asyncio.Event = asyncio.Event()
        self._write_available.set()  # Initially available

    async def acquire_read(self) -> None:
        """Acquire read lock (multiple readers allowed).

        This will block if a writer currently holds the lock.
        Multiple readers can acquire the lock simultaneously.
        """
        # Wait for write lock to be available
        await self._write_available.wait()

        # Acquire reader lock to safely increment counter
        async with self._reader_lock:
            self._readers += 1

    async def release_read(self) -> None:
        """Release read lock.

        Decrements the reader count and notifies waiting writers
        if this was the last reader.
        """
        async with self._no_readers:
            self._readers -= 1
            if self._readers == 0:
                # Notify waiting writers that no readers remain
                self._no_readers.notify_all()

    async def acquire_write(self) -> None:
        """Acquire write lock (exclusive).

        This will block until all readers have released their locks
        and no other writer holds the lock.
        """
        # First acquire the write lock to prevent other writers
        await self._write_lock.acquire()

        # Signal that write lock is being acquired
        self._write_available.clear()

        # Wait for all readers to finish
        async with self._no_readers:
            while self._readers > 0:
                await self._no_readers.wait()

    async def release_write(self) -> None:
        """Release write lock.

        Allows waiting readers and writers to proceed.
        """
        # Signal that write lock is available again
        self._write_available.set()

        # Release the lock
        self._write_lock.release()

    @asynccontextmanager
    async def read_lock(self) -> AsyncIterator[None]:
        """Context manager for read operations.

        Example:
            async with lock.read_lock():
                data = await db.query("SELECT ...")

        Yields:
            None
        """
        await self.acquire_read()
        try:
            yield
        finally:
            await self.release_read()

    @asynccontextmanager
    async def write_lock(self) -> AsyncIterator[None]:
        """Context manager for write operations.

        Example:
            async with lock.write_lock():
                await db.execute("INSERT INTO ...")

        Yields:
            None
        """
        await self.acquire_write()
        try:
            yield
        finally:
            await self.release_write()
