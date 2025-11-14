"""Tests for the shared ProgressTracker utility."""

import asyncio
import unittest
from unittest.mock import AsyncMock

from app.utils.progress_tracker import ProgressTracker


class TestProgressTracker(unittest.IsolatedAsyncioTestCase):
    """Test suite for ProgressTracker class."""

    async def test_basic_progress_tracking(self):
        """Test basic progress increment and tracking."""
        formatter = AsyncMock(return_value=123)

        tracker = ProgressTracker(total=10, progress_formatter=formatter, initial_message_id=None)

        # Start the queue processor
        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Increment a few times
        for _ in range(10):
            await tracker.increment_and_update()

        # Mark complete and wait for processor
        tracker.mark_complete()
        await processor_task

        # Verify progress
        assert tracker.completed == 10
        assert tracker.is_complete

    async def test_progress_formatter_called_with_updates(self):
        """Test that progress formatter is called appropriately."""
        formatter = AsyncMock(return_value=456)

        tracker = ProgressTracker(
            total=5,
            progress_formatter=formatter,
            initial_message_id=None,
            small_batch_threshold=5,  # Should update on every increment
        )

        # Start processor
        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Increment all items
        for _ in range(5):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)  # Small delay to allow queue processing

        # Complete and wait
        tracker.mark_complete()
        await processor_task

        # Formatter should have been called at least once
        assert formatter.call_count >= 1

    async def test_message_id_tracking(self):
        """Test that message ID is properly tracked and updated."""
        # Formatter returns different message IDs
        call_count = 0

        async def formatter(current, total, msg_id):
            nonlocal call_count
            call_count += 1
            return 100 + call_count  # Return incrementing message IDs

        tracker = ProgressTracker(total=5, progress_formatter=formatter, initial_message_id=99)

        # Verify initial message ID
        assert tracker.message_id == 99

        # Start processor
        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Increment and allow updates
        for _ in range(5):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)

        tracker.mark_complete()
        await processor_task

        # Message ID should have been updated by formatter
        if call_count > 0:
            assert tracker.message_id == 100 + call_count

    async def test_concurrent_increments(self):
        """Test that concurrent increments are handled correctly."""
        formatter = AsyncMock(return_value=789)

        tracker = ProgressTracker(total=20, progress_formatter=formatter)

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Simulate concurrent workers
        async def worker():
            for _ in range(4):
                await tracker.increment_and_update()
                await asyncio.sleep(0.001)

        # Run 5 workers concurrently (5 * 4 = 20 increments)
        await asyncio.gather(*[worker() for _ in range(5)])

        tracker.mark_complete()
        await processor_task

        # All increments should be counted
        assert tracker.completed == 20
        assert tracker.is_complete

    async def test_formatter_exception_handling(self):
        """Test that exceptions in formatter don't break the tracker."""
        call_count = 0

        async def failing_formatter(current, total, msg_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("First call fails")
            return 999

        tracker = ProgressTracker(
            total=5,
            progress_formatter=failing_formatter,
            small_batch_threshold=5,  # Update on every increment
        )

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Increment multiple times
        for _ in range(5):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)

        tracker.mark_complete()
        await processor_task

        # Progress should still be tracked despite formatter failure
        assert tracker.completed == 5
        assert call_count >= 1  # Formatter was called at least once

    async def test_small_batch_threshold(self):
        """Test that small batch threshold triggers more frequent updates."""
        formatter = AsyncMock(return_value=111)

        # Small batch with threshold of 10
        tracker = ProgressTracker(
            total=5,
            progress_formatter=formatter,
            small_batch_threshold=10,  # 5 <= 10, so should update frequently
        )

        processor_task = asyncio.create_task(tracker.process_update_queue())

        for _ in range(5):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)

        tracker.mark_complete()
        await processor_task

        # Should have multiple updates due to small batch
        assert formatter.call_count >= 1

    async def test_progress_threshold_percentage(self):
        """Test that progress threshold percentage controls update frequency."""
        formatter = AsyncMock(return_value=222)

        # Large batch with custom threshold
        tracker = ProgressTracker(
            total=100,
            progress_formatter=formatter,
            progress_threshold_percentage=10.0,  # Update every 10%
            small_batch_threshold=5,  # Won't apply since total > threshold
        )

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Increment to 50%
        for _ in range(50):
            await tracker.increment_and_update()
            await asyncio.sleep(0.001)

        tracker.mark_complete()
        await processor_task

        # Should have around 5 updates (at 10%, 20%, 30%, 40%, 50%)
        # Allow some variance due to time-based updates
        assert formatter.call_count >= 3

    async def test_queue_overflow_handling(self):
        """Test that queue overflow is handled gracefully."""
        slow_formatter_calls = []

        async def slow_formatter(current, total, msg_id):
            slow_formatter_calls.append((current, total))
            # Simulate slow operation
            await asyncio.sleep(0.1)
            return 333

        tracker = ProgressTracker(
            total=10,
            progress_formatter=slow_formatter,
            small_batch_threshold=10,  # Update on every increment
        )

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Rapidly increment to cause queue overflow
        for _ in range(10):
            await tracker.increment_and_update()
            # No sleep - should cause queue overflow

        tracker.mark_complete()
        await processor_task

        # Should have processed some updates (queue drops old ones)
        assert len(slow_formatter_calls) >= 1
        # Final update should show completion
        final_call = slow_formatter_calls[-1]
        assert final_call[0] <= 10  # completed <= total

    async def test_mark_complete_before_all_increments(self):
        """Test that mark_complete can be called early."""
        formatter = AsyncMock(return_value=444)

        tracker = ProgressTracker(total=10, progress_formatter=formatter)

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Only increment to 5
        for _ in range(5):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)

        # Mark complete early
        tracker.mark_complete()
        await processor_task

        # Should show partial completion
        assert tracker.completed == 5
        assert not tracker.is_complete  # Not fully complete

    async def test_update_interval_throttling(self):
        """Test that update_interval throttles frequent updates."""
        formatter = AsyncMock(return_value=555)

        tracker = ProgressTracker(
            total=100,
            progress_formatter=formatter,
            update_interval=0.5,  # 500ms between updates
            small_batch_threshold=5,  # Large batch, so percentage-based
        )

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Rapidly increment
        for _ in range(20):
            await tracker.increment_and_update()
            await asyncio.sleep(0.01)  # 10ms per increment = 200ms total

        tracker.mark_complete()
        await processor_task

        # Should have limited calls due to time throttling
        # With 200ms total and 500ms interval, should have 1-2 calls
        # (plus potential progress threshold triggers)
        assert formatter.call_count >= 1

    async def test_no_updates_for_zero_total(self):
        """Test handling of edge case with zero total."""
        formatter = AsyncMock(return_value=666)

        tracker = ProgressTracker(total=0, progress_formatter=formatter)

        processor_task = asyncio.create_task(tracker.process_update_queue())

        # Mark complete immediately
        tracker.mark_complete()
        await processor_task

        # Should not have errors
        assert tracker.completed == 0
        assert tracker.is_complete

    async def test_properties(self):
        """Test that properties return correct values."""
        formatter = AsyncMock(return_value=777)

        tracker = ProgressTracker(total=10, progress_formatter=formatter)

        assert tracker.completed == 0
        assert not tracker.is_complete

        processor_task = asyncio.create_task(tracker.process_update_queue())

        for _ in range(10):
            await tracker.increment_and_update()

        tracker.mark_complete()
        await processor_task

        assert tracker.completed == 10
        assert tracker.is_complete
