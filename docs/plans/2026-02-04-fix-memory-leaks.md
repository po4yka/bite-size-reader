# Fix Memory Leaks Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 memory leaks and 1 cancellation-safety bug identified in the architecture review.

**Architecture:** Minimal, focused patches to existing files. Each fix is independent. TTL-based eviction for unbounded dicts; `raise_if_cancelled` guard for retry loop. No new abstractions -- just add cleanup logic where it's missing.

**Tech Stack:** Python 3.13, asyncio, pytest, unittest

---

### Task 1: Add TTL eviction to BackgroundProcessor._local_locks

`_local_locks: dict[int, asyncio.Lock]` grows per `request_id` and is never cleaned. Over time this leaks memory proportional to total requests processed.

**Files:**
- Modify: `app/api/background_processor.py:78` and `_release_lock` method
- Test: `tests/api/test_background_processor.py`

**Step 1: Write the failing test**

Add to `tests/api/test_background_processor.py`:

```python
@pytest.mark.asyncio
async def test_local_locks_cleaned_after_release():
    """_local_locks entries are removed after lock release to prevent memory leaks."""
    cfg = _make_dummy_cfg()
    proc = BackgroundProcessor(
        cfg=cfg,
        db=MagicMock(),
        url_processor=MagicMock(),
        redis=None,
        semaphore=asyncio.Semaphore(3),
        audit_func=MagicMock(),
    )
    # Simulate acquiring a local lock
    lock = proc._local_locks.setdefault(42, asyncio.Lock())
    await lock.acquire()

    handle = LockHandle("local", "42", None, lock)
    await proc._release_lock(handle)

    assert 42 not in proc._local_locks, "_local_locks should remove entry after release"
```

You'll need to import `LockHandle` from the module. Check the file for the exact import path -- it's a dataclass defined in the same file.

**Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py::test_local_locks_cleaned_after_release -xvs`
Expected: FAIL -- `42` still in `_local_locks`

**Step 3: Implement the fix**

In `app/api/background_processor.py`, inside `_release_lock`, after the local lock release (line ~352), add cleanup:

```python
        elif handle.source == "local" and handle.local_lock and handle.local_lock.locked():
            handle.local_lock.release()

        # Clean up local lock entry to prevent memory leak
        if handle.source == "local":
            request_id = int(handle.key)
            lock_obj = self._local_locks.get(request_id)
            if lock_obj is not None and not lock_obj.locked():
                self._local_locks.pop(request_id, None)
```

**Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py::test_local_locks_cleaned_after_release -xvs`
Expected: PASS

**Step 5: Run full background processor test suite**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py -xvs`
Expected: All pass

**Step 6: Commit**

```bash
git add app/api/background_processor.py tests/api/test_background_processor.py
git commit -m "fix(background): clean up _local_locks after release to prevent memory leak"
```

---

### Task 2: Add TTL expiry to URLHandler._awaiting_url_users and _pending_multi_links

Users who send `/summarize` but never follow up with a URL remain in `_awaiting_url_users` forever. Similarly `_pending_multi_links` entries for abandoned confirmations never expire.

**Files:**
- Modify: `app/adapters/telegram/url_handler.py:37-56`
- Test: `tests/test_url_handler.py`

**Step 1: Write the failing test**

Add to `tests/test_url_handler.py`:

```python
import time
from unittest.mock import patch


@pytest.mark.asyncio
async def test_awaiting_users_expire_after_ttl() -> None:
    """Users in _awaiting_url_users should expire after TTL."""
    handler = URLHandler(
        db=cast("Database", SimpleNamespace()),  # type: ignore[arg-type]
        response_formatter=cast(
            "ResponseFormatter",
            SimpleNamespace(MAX_BATCH_URLS=5, safe_reply=AsyncMock()),
        ),
        url_processor=cast("URLProcessor", SimpleNamespace()),
    )

    await handler.add_awaiting_user(100)
    assert await handler.is_awaiting_url(100)

    # Simulate time passing beyond TTL (default 120s)
    with patch("time.time", return_value=time.time() + 130):
        assert not await handler.is_awaiting_url(100), "Should have expired"


@pytest.mark.asyncio
async def test_pending_multi_links_expire_after_ttl() -> None:
    """Entries in _pending_multi_links should expire after TTL."""
    handler = URLHandler(
        db=cast("Database", SimpleNamespace()),  # type: ignore[arg-type]
        response_formatter=cast(
            "ResponseFormatter",
            SimpleNamespace(MAX_BATCH_URLS=5, safe_reply=AsyncMock()),
        ),
        url_processor=cast("URLProcessor", SimpleNamespace()),
    )

    await handler.add_pending_multi_links(200, ["https://a.com", "https://b.com"])
    assert await handler.has_pending_multi_links(200)

    with patch("time.time", return_value=time.time() + 130):
        assert not await handler.has_pending_multi_links(200), "Should have expired"


@pytest.mark.asyncio
async def test_cleanup_expired_state() -> None:
    """cleanup_expired_state removes stale entries."""
    handler = URLHandler(
        db=cast("Database", SimpleNamespace()),  # type: ignore[arg-type]
        response_formatter=cast(
            "ResponseFormatter",
            SimpleNamespace(MAX_BATCH_URLS=5, safe_reply=AsyncMock()),
        ),
        url_processor=cast("URLProcessor", SimpleNamespace()),
    )

    await handler.add_awaiting_user(100)
    await handler.add_pending_multi_links(200, ["https://a.com"])

    with patch("time.time", return_value=time.time() + 130):
        cleaned = await handler.cleanup_expired_state()
        assert cleaned == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_url_handler.py -xvs -k "expire or cleanup_expired_state"`
Expected: FAIL -- methods don't exist yet

**Step 3: Implement the fix**

In `app/adapters/telegram/url_handler.py`, change the state storage from bare sets/dicts to timestamped entries:

Replace lines 53-56:
```python
        # Simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # Pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}
```

With:
```python
        # In-memory state with timestamps for TTL expiry
        self._state_ttl_sec = 120  # 2 minutes
        # uid -> timestamp when added
        self._awaiting_url_users: dict[int, float] = {}
        # uid -> (urls, timestamp)
        self._pending_multi_links: dict[int, tuple[list[str], float]] = {}
```

Then update all methods that read/write these dicts:

`add_awaiting_user`:
```python
    async def add_awaiting_user(self, uid: int) -> None:
        async with self._state_lock:
            self._awaiting_url_users[uid] = time.time()
```

`add_pending_multi_links`:
```python
    async def add_pending_multi_links(self, uid: int, urls: list[str]) -> None:
        async with self._state_lock:
            self._pending_multi_links[uid] = (urls, time.time())
```

`cancel_pending_requests` -- update to work with new types:
```python
    async def cancel_pending_requests(self, uid: int) -> tuple[bool, bool]:
        async with self._state_lock:
            awaiting_cancelled = uid in self._awaiting_url_users
            if awaiting_cancelled:
                self._awaiting_url_users.pop(uid, None)

            multi_cancelled = uid in self._pending_multi_links
            if multi_cancelled:
                self._pending_multi_links.pop(uid, None)

            return awaiting_cancelled, multi_cancelled
```

`handle_awaited_url` -- line 92-93, change discard to pop:
```python
        async with self._state_lock:
            self._awaiting_url_users.pop(uid, None)
```

Add new query methods:
```python
    async def is_awaiting_url(self, uid: int) -> bool:
        async with self._state_lock:
            ts = self._awaiting_url_users.get(uid)
            if ts is None:
                return False
            if time.time() - ts > self._state_ttl_sec:
                self._awaiting_url_users.pop(uid, None)
                return False
            return True

    async def has_pending_multi_links(self, uid: int) -> bool:
        async with self._state_lock:
            entry = self._pending_multi_links.get(uid)
            if entry is None:
                return False
            if time.time() - entry[1] > self._state_ttl_sec:
                self._pending_multi_links.pop(uid, None)
                return False
            return True

    async def cleanup_expired_state(self) -> int:
        """Remove expired awaiting/pending entries. Returns count removed."""
        async with self._state_lock:
            now = time.time()
            cleaned = 0
            expired_awaiting = [
                uid for uid, ts in self._awaiting_url_users.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_awaiting:
                del self._awaiting_url_users[uid]
                cleaned += 1
            expired_multi = [
                uid for uid, (_, ts) in self._pending_multi_links.items()
                if now - ts > self._state_ttl_sec
            ]
            for uid in expired_multi:
                del self._pending_multi_links[uid]
                cleaned += 1
            return cleaned
```

Then find all callers that check membership (search for `_awaiting_url_users` and `_pending_multi_links` in `message_router.py`, `message_router_helpers.py`, and `url_handler.py` itself) and update them to use the new timestamped structure. Key patterns:

- `uid in self._awaiting_url_users` stays the same (dict membership check)
- `self._awaiting_url_users.discard(uid)` becomes `self._awaiting_url_users.pop(uid, None)`
- `self._pending_multi_links[uid]` now returns `(urls, timestamp)` -- callers must unpack

**Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_url_handler.py -xvs`
Expected: All pass (old tests + new ones)

**Step 5: Wire cleanup into existing cleanup loop**

In `app/adapters/telegram/telegram_bot.py`, inside `_run_rate_limiter_cleanup_loop` (line ~449), add URL handler cleanup after rate limiter cleanup:

```python
                    cleaned = await self.message_handler.message_router.cleanup_rate_limiter()
                    # Also clean up expired URL handler state
                    if hasattr(self.message_handler, "url_handler"):
                        url_cleaned = await self.message_handler.url_handler.cleanup_expired_state()
                        if url_cleaned > 0:
                            logger.debug(
                                "url_handler_state_cleanup_completed",
                                extra={"entries_cleaned": url_cleaned},
                            )
```

**Step 6: Run full test suite for affected modules**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_url_handler.py tests/test_rate_limiter.py -xvs`
Expected: All pass

**Step 7: Commit**

```bash
git add app/adapters/telegram/url_handler.py app/adapters/telegram/telegram_bot.py tests/test_url_handler.py
git commit -m "fix(telegram): add TTL expiry to URL handler state to prevent memory leaks"
```

---

### Task 3: Add cleanup for _rate_limit_notified_until in MessageRouter

`_rate_limit_notified_until` is cleaned only when the rate limiter cleanup runs, but it accumulates user IDs without bounds between runs.

**Files:**
- Modify: `app/adapters/telegram/message_router.py:134-140`
- Test: `tests/test_rate_limiter.py` (or new test file)

**Step 1: Write the failing test**

Add to `tests/test_rate_limiter.py`:

```python
class TestMessageRouterCleanup(unittest.IsolatedAsyncioTestCase):
    """Test message router cleans up notification state."""

    async def test_cleanup_removes_expired_notifications(self):
        """cleanup_rate_limiter should also clean _rate_limit_notified_until."""
        from unittest.mock import MagicMock, AsyncMock
        from app.adapters.telegram.message_router import MessageRouter

        cfg = MagicMock()
        cfg.api_limits.requests_limit = 10
        cfg.api_limits.window_seconds = 60
        cfg.api_limits.max_concurrent = 3
        cfg.api_limits.cooldown_multiplier = 1.0

        router = MessageRouter(
            cfg=cfg,
            db=MagicMock(),
            access_controller=MagicMock(),
            command_processor=MagicMock(),
            url_handler=MagicMock(),
            forward_processor=MagicMock(),
            response_formatter=MagicMock(),
            audit_func=MagicMock(),
        )

        now = time.time()
        # Add expired entries (deadline in the past)
        router._rate_limit_notified_until[111] = now - 100
        router._rate_limit_notified_until[222] = now - 50
        # Add active entry (deadline in the future)
        router._rate_limit_notified_until[333] = now + 100

        await router.cleanup_rate_limiter()

        assert 111 not in router._rate_limit_notified_until
        assert 222 not in router._rate_limit_notified_until
        assert 333 in router._rate_limit_notified_until
```

**Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_rate_limiter.py::TestMessageRouterCleanup -xvs`
Expected: FAIL -- expired entries still present

**Step 3: Implement the fix**

In `app/adapters/telegram/message_router.py`, expand `cleanup_rate_limiter`:

```python
    async def cleanup_rate_limiter(self) -> int:
        """Clean up expired rate limiter entries to prevent memory leaks.

        Only cleans up the in-memory rate limiter; Redis handles TTL automatically.
        Also cleans up expired notification-suppression and recent message entries.
        Returns the number of users cleaned up.
        """
        cleaned = await self._rate_limiter.cleanup_expired()

        # Clean up expired rate-limit notification suppression entries
        now = time.time()
        expired_notifs = [
            uid for uid, deadline in self._rate_limit_notified_until.items() if now >= deadline
        ]
        for uid in expired_notifs:
            del self._rate_limit_notified_until[uid]

        # Clean up expired recent message IDs
        cutoff = now - self._recent_message_ttl
        expired_msgs = [
            key for key, (ts, _sig) in self._recent_message_ids.items() if ts < cutoff
        ]
        for key in expired_msgs:
            del self._recent_message_ids[key]

        return cleaned
```

**Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/test_rate_limiter.py -xvs`
Expected: All pass

**Step 5: Commit**

```bash
git add app/adapters/telegram/message_router.py tests/test_rate_limiter.py
git commit -m "fix(telegram): clean up expired notification and message-dedup state in cleanup loop"
```

---

### Task 4: Add raise_if_cancelled to BackgroundProcessor._run_with_backoff

The retry loop catches all `Exception` including `asyncio.CancelledError`, causing cancelled tasks to retry instead of propagating cancellation.

**Files:**
- Modify: `app/api/background_processor.py:467-503`
- Test: `tests/api/test_background_processor.py`

**Step 1: Write the failing test**

Add to `tests/api/test_background_processor.py`:

```python
@pytest.mark.asyncio
async def test_run_with_backoff_propagates_cancellation():
    """_run_with_backoff should re-raise CancelledError immediately, not retry."""
    cfg = _make_dummy_cfg()
    proc = BackgroundProcessor(
        cfg=cfg,
        db=MagicMock(),
        url_processor=MagicMock(),
        redis=None,
        semaphore=asyncio.Semaphore(3),
        audit_func=MagicMock(),
    )

    call_count = 0

    async def cancelling_func():
        nonlocal call_count
        call_count += 1
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await proc._run_with_backoff(cancelling_func, "test_stage", "cid-123")

    assert call_count == 1, "Should not retry on CancelledError"
```

You may need a helper `_make_dummy_cfg()` if one doesn't exist. Check the existing test file for how `BackgroundProcessor` is instantiated in other tests and replicate that pattern.

**Step 2: Run test to verify it fails**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py::test_run_with_backoff_propagates_cancellation -xvs`
Expected: FAIL -- `CancelledError` is caught and retried

**Step 3: Implement the fix**

In `app/api/background_processor.py`, add the import at the top (if not already present):

```python
from app.core.async_utils import raise_if_cancelled
```

Then in `_run_with_backoff`, add the guard at the top of the `except` block (line ~477):

```python
    async def _run_with_backoff(
        self,
        func: Callable[[], Awaitable[Any]],
        stage: str,
        correlation_id: str,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._retry.attempts + 1):
            try:
                return await func()
            except Exception as exc:
                raise_if_cancelled(exc)
                last_error = exc
                # ... rest unchanged
```

**Step 4: Run test to verify it passes**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py::test_run_with_backoff_propagates_cancellation -xvs`
Expected: PASS

**Step 5: Run full background processor test suite**

Run: `cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/api/test_background_processor.py -xvs`
Expected: All pass

**Step 6: Commit**

```bash
git add app/api/background_processor.py tests/api/test_background_processor.py
git commit -m "fix(background): propagate CancelledError in retry loop instead of retrying"
```

---

### Task 5: Final verification

**Step 1: Run lint and type check**

```bash
cd /mnt/nvme/home/po4yka/bite-size-reader && make format && make lint && make type
```

Fix any issues.

**Step 2: Run full test suite**

```bash
cd /mnt/nvme/home/po4yka/bite-size-reader && python -m pytest tests/ -x --timeout=60
```

All tests should pass.

**Step 3: Final commit (if lint/format changed anything)**

```bash
git add -u
git commit -m "chore: format after memory leak fixes"
```
