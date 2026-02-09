import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from app.api.background_processor import BackgroundProcessor
from app.di.background import build_background_processor


class DummyBackgroundConfig:
    def __init__(
        self,
        *,
        lock_enabled: bool = True,
        lock_required: bool = False,
        lock_skip_on_held: bool = True,
        lock_ttl_ms: int = 300_000,
        retry_attempts: int = 3,
        base_delay_ms: int = 50,
        max_delay_ms: int = 200,
        jitter_ratio: float = 0.0,
    ) -> None:
        self.redis_lock_enabled = lock_enabled
        self.redis_lock_required = lock_required
        self.lock_skip_on_held = lock_skip_on_held
        self.lock_ttl_ms = lock_ttl_ms
        self.retry_attempts = retry_attempts
        self.retry_base_delay_ms = base_delay_ms
        self.retry_max_delay_ms = max_delay_ms
        self.retry_jitter_ratio = jitter_ratio


class DummyRedisConfig:
    def __init__(
        self, *, prefix: str = "test", enabled: bool = True, required: bool = False
    ) -> None:
        self.prefix = prefix
        self.enabled = enabled
        self.required = required


class DummyRuntimeConfig:
    def __init__(self, *, preferred_lang: str = "auto", max_concurrent_calls: int = 3) -> None:
        self.preferred_lang = preferred_lang
        self.max_concurrent_calls = max_concurrent_calls
        self.db_path = ":memory:"


class DummyDatabaseConfig:
    def __init__(self) -> None:
        self.operation_timeout = 30.0
        self.max_retries = 3
        self.json_max_size = 10_000_000
        self.json_max_depth = 20
        self.json_max_array_length = 10_000
        self.json_max_dict_keys = 1_000


class DummyCfg:
    def __init__(self) -> None:
        self.background = DummyBackgroundConfig()
        self.redis = DummyRedisConfig()
        self.runtime = DummyRuntimeConfig()
        self.database = DummyDatabaseConfig()


class StubDB:
    def __init__(self) -> None:
        self.summaries: dict[int, Any] = {}

    def upsert_summary(
        self, *, request_id: int, lang: str, json_payload: Any, is_read: bool
    ) -> None:
        self.summaries[request_id] = {
            "lang": lang,
            "json": json_payload,
            "is_read": is_read,
        }


class StubExtractor:
    def __init__(self, content: str = "hello world") -> None:
        self._content = content
        self.firecrawl = object()

    async def extract_content_pure(
        self, url: str, correlation_id: str | None = None
    ) -> tuple[str, str, dict[str, Any]]:
        return self._content, "markdown", {"url": url, "cid": correlation_id}


class StubSummarizer:
    def __init__(self, summary: Any | None = None, *, fail: bool = False) -> None:
        self._summary = summary or {"ok": True}
        self.fail = fail
        self.calls = 0
        self.openrouter = object()

    async def summarize_content_pure(
        self,
        *,
        content_text: str,
        chosen_lang: str,
        system_prompt: str,
        correlation_id: str | None = None,
    ) -> Any:
        self.calls += 1
        if self.fail:
            raise RuntimeError("fail_summarize")
        return self._summary


class StubURLProcessor:
    def __init__(self, extractor: StubExtractor, summarizer: StubSummarizer) -> None:
        self.content_extractor = extractor
        self.llm_summarizer = summarizer
        self.response_formatter = object()


@pytest.mark.asyncio
async def test_di_builder_creates_processor_with_semaphore(monkeypatch):
    monkeypatch.setenv("API_ID", "1")
    monkeypatch.setenv("API_HASH", "test_api_hash_placeholder_value___")
    monkeypatch.setenv("BOT_TOKEN", "1000000000:TESTTOKENPLACEHOLDER1234567890ABC")
    monkeypatch.setenv("ALLOWED_USER_IDS", "1")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or_test_key")
    monkeypatch.setenv("DB_PATH", "/tmp/bsr-bg-test.db")

    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def fake_get_redis(cfg: Any) -> fakeredis.aioredis.FakeRedis:
        return redis_client

    monkeypatch.setattr("app.infrastructure.redis.get_redis", fake_get_redis)

    processor = await build_background_processor()
    assert processor is not None
    # Semaphore capacity respects runtime max_concurrent_calls default (4)
    assert isinstance(processor._sem, asyncio.Semaphore)

    await redis_client.flushall()


@pytest.mark.asyncio
async def test_lock_skip_when_redis_key_held(monkeypatch):
    cfg = DummyCfg()
    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis_client.set(f"{cfg.redis.prefix}:bg:req:1", "held", px=cfg.background.lock_ttl_ms)

    db = StubDB()
    processor = BackgroundProcessor(
        cfg=cfg,
        db=db,
        url_processor=StubURLProcessor(StubExtractor(), StubSummarizer()),
        redis=redis_client,
        semaphore=asyncio.Semaphore(2),
        audit_func=lambda *_args, **_kwargs: None,
    )

    # Mock repositories
    processor.request_repo = MagicMock()
    processor.request_repo.async_get_request_by_id = AsyncMock(
        return_value={"id": 1, "type": "url", "input_url": "https://example.com"}
    )
    processor.summary_repo = MagicMock()
    processor.summary_repo.async_get_summary_by_request = AsyncMock(return_value=None)

    await processor.process(1, correlation_id="cid-lock")
    assert db.summaries == {}


@pytest.mark.asyncio
async def test_local_lock_fallback_and_success(monkeypatch):
    cfg = DummyCfg()
    db = StubDB()
    processor = BackgroundProcessor(
        cfg=cfg,
        db=db,
        url_processor=StubURLProcessor(StubExtractor(), StubSummarizer()),
        redis=None,
        semaphore=asyncio.Semaphore(2),
        audit_func=lambda *_args, **_kwargs: None,
    )

    # Mock repositories
    processor.request_repo = MagicMock()
    processor.request_repo.async_get_request_by_id = AsyncMock(
        return_value={
            "id": 2,
            "type": "url",
            "input_url": "https://example.com",
            "correlation_id": "cid-local",
        }
    )
    processor.request_repo.async_update_request_status_with_correlation = AsyncMock()

    processor.summary_repo = MagicMock()
    processor.summary_repo.async_get_summary_by_request = AsyncMock(return_value=None)

    async def fake_upsert(**kwargs):
        db.upsert_summary(
            request_id=kwargs["request_id"],
            lang=kwargs["lang"],
            json_payload=kwargs["json_payload"],
            is_read=kwargs["is_read"],
        )

    processor.summary_repo.async_upsert_summary = AsyncMock(side_effect=fake_upsert)

    await processor.process(2, correlation_id="cid-local")
    assert db.summaries.get(2) is not None
    # Check that status update was called
    assert processor.request_repo.async_update_request_status_with_correlation.called


@pytest.mark.asyncio
async def test_retries_and_error_status(monkeypatch):
    cfg = DummyCfg()
    cfg.background.retry_attempts = 2
    cfg.background.retry_base_delay_ms = 1
    cfg.background.retry_max_delay_ms = 2

    db = StubDB()
    failing_summarizer = StubSummarizer(fail=True)
    processor = BackgroundProcessor(
        cfg=cfg,
        db=db,
        url_processor=StubURLProcessor(StubExtractor(), failing_summarizer),
        redis=None,
        semaphore=asyncio.Semaphore(1),
        audit_func=lambda *_args, **_kwargs: None,
    )

    # Mock repositories
    processor.request_repo = MagicMock()
    processor.request_repo.async_get_request_by_id = AsyncMock(
        return_value={
            "id": 3,
            "type": "forward",
            "content_text": "hello",
            "correlation_id": "cid-error",
        }
    )
    status_updates = []

    async def fake_update_status(rid, status, cid):
        status_updates.append(status)

    processor.request_repo.async_update_request_status_with_correlation = AsyncMock(
        side_effect=fake_update_status
    )

    processor.summary_repo = MagicMock()
    processor.summary_repo.async_get_summary_by_request = AsyncMock(return_value=None)

    await processor.process(3, correlation_id="cid-error")
    # No summary written and status marked error
    assert db.summaries.get(3) is None
    assert status_updates[-1] == "error"
    assert failing_summarizer.calls == cfg.background.retry_attempts


@pytest.mark.asyncio
async def test_local_locks_cleaned_after_release():
    """_local_locks entries must be removed after lock release to prevent memory leak."""
    from app.api.background_processor import LockHandle

    cfg = DummyCfg()
    processor = BackgroundProcessor(
        cfg=cfg,
        db=StubDB(),
        url_processor=StubURLProcessor(StubExtractor(), StubSummarizer()),
        redis=None,
        semaphore=asyncio.Semaphore(1),
        audit_func=lambda *_args, **_kwargs: None,
    )

    request_id = 42
    lock = asyncio.Lock()
    await lock.acquire()
    processor._local_locks[request_id] = lock

    handle = LockHandle(source="local", key=str(request_id), token=None, local_lock=lock)
    await processor._release_lock(handle)

    assert request_id not in processor._local_locks, (
        f"_local_locks still contains request_id={request_id} after release"
    )


@pytest.mark.asyncio
async def test_run_with_backoff_propagates_cancellation():
    """_run_with_backoff should re-raise CancelledError immediately, not retry."""
    cfg = DummyCfg()
    cfg.background.retry_attempts = 3
    cfg.background.retry_base_delay_ms = 1
    cfg.background.retry_max_delay_ms = 2

    proc = BackgroundProcessor(
        cfg=cfg,
        db=StubDB(),
        url_processor=StubURLProcessor(StubExtractor(), StubSummarizer()),
        redis=None,
        semaphore=asyncio.Semaphore(3),
        audit_func=lambda *_args, **_kwargs: None,
    )

    call_count = 0

    async def cancelling_func():
        nonlocal call_count
        call_count += 1
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await proc._run_with_backoff(cancelling_func, "test_stage", "cid-123")

    assert call_count == 1, "Should not retry on CancelledError"
