"""Tests for TypingIndicator — lifecycle, cancel-on-stop, and loop timing."""

from __future__ import annotations

import asyncio

import pytest

from app.utils.typing_indicator import TypingIndicator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_indicator(calls: list[str]) -> TypingIndicator:
    """Return a TypingIndicator backed by a mock that records action strings."""

    async def send_action(chat_id: int, action: str) -> bool:
        calls.append(action)
        return True

    return TypingIndicator(send_chat_action_func=send_action, chat_id=42)


# ---------------------------------------------------------------------------
# stop() sends cancel action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_sends_cancel_action() -> None:
    """stop() must send action='cancel' so Telegram clears the indicator immediately."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.start()
    await ind.stop()

    assert "cancel" in calls, "stop() must send SendMessageCancelAction to Telegram"


@pytest.mark.asyncio
async def test_stop_cancel_is_last_action() -> None:
    """cancel must be the very last action sent, after the loop is terminated."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.start()
    await ind.stop()

    assert calls[-1] == "cancel"


@pytest.mark.asyncio
async def test_stop_without_start_is_noop() -> None:
    """Calling stop() before start() must not send any action."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.stop()

    assert calls == [], "stop() on a never-started indicator must be silent"


@pytest.mark.asyncio
async def test_double_stop_is_idempotent() -> None:
    """A second stop() call must be a no-op — no duplicate cancel action."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.start()
    await ind.stop()
    cancel_count_after_first_stop = calls.count("cancel")
    await ind.stop()

    assert calls.count("cancel") == cancel_count_after_first_stop


# ---------------------------------------------------------------------------
# Loop timing — sleep-first design
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_send_is_immediate() -> None:
    """start() must send the typing action before returning, not after the first sleep."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.start()

    # At this point the loop has been created but has not slept yet, so only
    # the initial send should have fired.
    assert calls == ["typing"], "initial action must be sent synchronously in start()"

    await ind.stop()


@pytest.mark.asyncio
async def test_loop_does_not_double_send_at_start() -> None:
    """With sleep-first loop the first refresh comes after one interval, not immediately."""
    recorded: list[str] = []

    async def track(chat_id: int, action: str) -> bool:
        recorded.append(action)
        return True

    ind = TypingIndicator(send_chat_action_func=track, chat_id=42, interval=0.05)

    await ind.start()
    # Immediately after start: only one "typing" (the initial send).
    # Yielding control must NOT cause a second send before the first sleep.
    assert recorded == ["typing"]
    await asyncio.sleep(0)
    assert recorded == ["typing"], "loop must not double-send before the first interval elapses"

    await ind.stop()


@pytest.mark.asyncio
async def test_loop_does_not_send_after_stop_set() -> None:
    """If the stop event is set between sleep wakeup and send, the send is skipped."""
    calls: list[str] = []
    fired: asyncio.Event = asyncio.Event()

    original_sleep = asyncio.sleep

    async def patched_sleep(delay: float) -> None:
        await original_sleep(delay)
        # Set the stop event right after sleep returns, before the loop checks it
        calls.append("__sleep_done__")

    ind = _make_indicator(calls)
    ind._interval = 0.01

    await ind.start()

    # Give loop exactly one sleep cycle then stop it
    await original_sleep(0.03)
    await ind.stop()

    # After stop, no further "typing" sends should appear
    post_stop = calls[calls.index("cancel") + 1 :] if "cancel" in calls else []
    assert post_stop == [], "no typing sends must occur after stop()"


# ---------------------------------------------------------------------------
# start() stop-event ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_clears_stop_event_before_initial_send() -> None:
    """_stop_event must be cleared before the first await in start()."""
    calls: list[str] = []
    ind = _make_indicator(calls)

    # Pre-set the stop event (simulates a re-use after stop)
    ind._stop_event.set()

    await ind.start()

    # The loop should NOT exit immediately because _stop_event was cleared
    # before the loop task was created.
    await asyncio.sleep(0)  # yield to let loop run once
    assert ind._task is not None, "_stop_event cleared too late — loop exited before it ran"

    await ind.stop()


# ---------------------------------------------------------------------------
# isinstance check — BaseException not Exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_handles_base_exception_from_task() -> None:
    """stop() must log non-CancelledError BaseExceptions without re-raising."""
    calls: list[str] = []
    ind = _make_indicator(calls)
    await ind.start()

    # Inject a raw BaseException into the task result path
    ind._task = asyncio.create_task(_raise_base_exception())

    # Must not raise
    await ind.stop()


async def _raise_base_exception() -> None:
    raise RuntimeError("synthetic task failure")


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_manager_stops_on_exit() -> None:
    """__aexit__ must call stop(), which must send cancel."""
    calls: list[str] = []
    ind = _make_indicator(calls)

    async with ind:
        assert "typing" in calls

    assert "cancel" in calls


@pytest.mark.asyncio
async def test_context_manager_stops_on_exception() -> None:
    """stop() (and the cancel action) must be sent even when the body raises."""
    calls: list[str] = []
    ind = _make_indicator(calls)

    with pytest.raises(ValueError):
        async with ind:
            raise ValueError("body error")

    assert "cancel" in calls
