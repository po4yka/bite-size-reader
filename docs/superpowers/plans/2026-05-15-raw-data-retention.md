# Raw Data Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-subsystem configurable TTL purging that NULLs raw artifact columns (HTML, LLM payloads, Telegram raw JSON, transcripts) while preserving all summary, cost, and metadata rows.

**Architecture:** A `RetentionConfig` Pydantic model wires into `AppConfig`. A Taskiq task `ratatoskr.data.purge` runs daily via the existing scheduler, acquiring a Redis distributed lock, then executing one batched UPDATE per subsystem. All targeted columns are already `nullable=True`; no Alembic migration is needed.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 asyncpg, Taskiq, Redis, Pydantic BaseModel, pytest-asyncio

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `app/config/retention.py` | `RetentionConfig` Pydantic model |
| Modify | `app/config/__init__.py` | re-export `RetentionConfig` |
| Modify | `app/config/settings.py` | wire `retention` into `AppConfig` + `Settings` |
| Create | `app/tasks/purge_raw_data.py` | Taskiq task + per-subsystem purge helpers |
| Modify | `app/tasks/scheduler.py` | register `ratatoskr.data.purge` cron |
| Create | `tests/tasks/test_purge_raw_data.py` | unit tests (mocked DB) |
| Modify | `docs/reference/environment-variables.md` | new `## Data Retention` section |

---

## Task 1: RetentionConfig

**Files:**
- Create: `app/config/retention.py`
- Modify: `app/config/__init__.py` (add export)
- Modify: `app/config/settings.py` (wire into `AppConfig` + `Settings`)

- [ ] **Step 1: Create `app/config/retention.py`**

```python
"""Retention policy configuration for raw artifact purge."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetentionConfig(BaseModel):
    """Per-subsystem TTL-based raw-data retention policy.

    A TTL of 0 means "never purge" for that subsystem.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="RETENTION_ENABLED",
        description="Master switch; when False no purge runs.",
    )
    cron: str = Field(
        default="0 3 * * *",
        validation_alias="RETENTION_CRON",
        description="UTC cron expression for the daily purge job.",
    )
    batch_size: int = Field(
        default=500,
        validation_alias="RETENTION_BATCH_SIZE",
        description="Max rows updated per subsystem per run.",
    )

    telegram_raw_days: int = Field(
        default=30,
        validation_alias="RETENTION_TELEGRAM_RAW_DAYS",
        description="Days to keep telegram_messages raw columns. 0 = never purge.",
    )
    crawl_content_days: int = Field(
        default=7,
        validation_alias="RETENTION_CRAWL_CONTENT_DAYS",
        description="Days to keep crawl_results content columns. 0 = never purge.",
    )
    llm_payload_days: int = Field(
        default=90,
        validation_alias="RETENTION_LLM_PAYLOAD_DAYS",
        description="Days to keep llm_calls request/response columns. 0 = never purge.",
    )
    video_transcript_days: int = Field(
        default=30,
        validation_alias="RETENTION_VIDEO_TRANSCRIPT_DAYS",
        description="Days to keep video_downloads.transcript_text. 0 = never purge.",
    )
    interaction_text_days: int = Field(
        default=30,
        validation_alias="RETENTION_INTERACTION_TEXT_DAYS",
        description="Days to keep user_interactions.input_text. 0 = never purge.",
    )
    request_content_days: int = Field(
        default=30,
        validation_alias="RETENTION_REQUEST_CONTENT_DAYS",
        description="Days to keep requests.content_text + error_context_json. 0 = never purge.",
    )
```

- [ ] **Step 2: Add export to `app/config/__init__.py`**

Find the block of imports and add after the `from .redis import RedisConfig` line:

```python
from .retention import RetentionConfig
```

- [ ] **Step 3: Wire `RetentionConfig` into `AppConfig` and `Settings` in `app/config/settings.py`**

Add the import at the top with the other config imports:
```python
from .retention import RetentionConfig
```

In the `AppConfig` dataclass (around line 193, after `vector_reconcile`), add:
```python
    retention: RetentionConfig = field(default_factory=RetentionConfig)
```

In the `Settings` class (around line 248, after `vector_reconcile`), add:
```python
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
```

In `Settings.as_app_config()` (around line 388, after `vector_reconcile=self.vector_reconcile`), add:
```python
            retention=self.retention,
```

- [ ] **Step 4: Verify config loads with defaults**

```bash
source .venv/bin/activate
python -c "
import os; os.environ.setdefault('API_ID','1'); os.environ.setdefault('API_HASH','x')
os.environ.setdefault('BOT_TOKEN','1:x'); os.environ.setdefault('ALLOWED_USER_IDS','1')
os.environ.setdefault('OPENROUTER_API_KEY','x'); os.environ.setdefault('DATABASE_URL','postgresql+asyncpg://x/y')
from app.config.retention import RetentionConfig
cfg = RetentionConfig()
assert cfg.enabled is True
assert cfg.crawl_content_days == 7
assert cfg.llm_payload_days == 90
print('RetentionConfig OK:', cfg)
"
```

Expected: prints `RetentionConfig OK: ...` with no exception.

- [ ] **Step 5: Commit**

```bash
git add app/config/retention.py app/config/__init__.py app/config/settings.py
git commit -m "feat(config): add RetentionConfig for per-subsystem raw-data TTLs"
```

---

## Task 2: Purge Task

**Files:**
- Create: `app/tasks/purge_raw_data.py`

- [ ] **Step 1: Write the failing import test** (verify module structure before filling in logic)

```bash
python -c "import app.tasks.purge_raw_data" 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'app.tasks.purge_raw_data'`

- [ ] **Step 2: Create `app/tasks/purge_raw_data.py`**

```python
"""Taskiq task: scheduled raw-artifact field purge.

NULLs heavy raw columns (HTML, LLM payloads, Telegram message JSON,
transcripts) once they age past their configured TTL. The containing row
is never deleted — cost, status, and metadata columns survive.

All targeted columns are already nullable=True; no migration is needed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select, update
from taskiq import TaskiqDepends

from app.config import AppConfig  # noqa: TC001 — taskiq resolves at runtime
from app.core.logging_utils import get_logger
from app.db.models import (
    CrawlResult,
    LLMCall,
    Request,
    TelegramMessage,
    UserInteraction,
    VideoDownload,
)
from app.db.session import Database  # noqa: TC001 — taskiq resolves at runtime
from app.infrastructure.locks.redis_lock import RedisDistributedLock
from app.infrastructure.redis import get_redis
from app.tasks.broker import broker
from app.tasks.deps import get_app_config, get_db

logger = get_logger(__name__)

_PURGE_LOCK_KEY = "task_lock:data_purge"
# 10 minutes: covers 6 subsystems × batch_size=500 rows each with room to spare.
_PURGE_LOCK_TTL = 600


@dataclass
class PurgeStats:
    """Per-subsystem counts of rows that had at least one field NULLed."""

    telegram_raw: int = field(default=0)
    crawl_content: int = field(default=0)
    llm_payload: int = field(default=0)
    video_transcript: int = field(default=0)
    interaction_text: int = field(default=0)
    request_content: int = field(default=0)


@broker.task(task_name="ratatoskr.data.purge")
async def purge_raw_data(
    cfg: AppConfig = TaskiqDepends(get_app_config),
    db: Database = TaskiqDepends(get_db),
) -> PurgeStats:
    """Acquire Redis lock and delegate to _purge_body."""
    redis_client = await get_redis(cfg)
    async with RedisDistributedLock(
        redis_client, _PURGE_LOCK_KEY, _PURGE_LOCK_TTL
    ) as acquired:
        if not acquired:
            logger.info(
                "data_purge_skipped_lock_held",
                extra={"key": _PURGE_LOCK_KEY},
            )
            return PurgeStats()
        return await _purge_body(cfg, db)


async def _purge_body(cfg: AppConfig, db: Database) -> PurgeStats:
    """Execute all subsystem purges and return aggregate stats."""
    if not cfg.retention.enabled:
        logger.info("data_purge_disabled")
        return PurgeStats()

    ret = cfg.retention
    batch = ret.batch_size
    now = dt.datetime.now(dt.timezone.utc)

    stats = PurgeStats(
        telegram_raw=await _purge_telegram_raw(db, now, ret.telegram_raw_days, batch),
        crawl_content=await _purge_crawl_content(db, now, ret.crawl_content_days, batch),
        llm_payload=await _purge_llm_payload(db, now, ret.llm_payload_days, batch),
        video_transcript=await _purge_video_transcript(
            db, now, ret.video_transcript_days, batch
        ),
        interaction_text=await _purge_interaction_text(
            db, now, ret.interaction_text_days, batch
        ),
        request_content=await _purge_request_content(
            db, now, ret.request_content_days, batch
        ),
    )
    logger.info(
        "data_purge_complete",
        extra={
            "telegram_raw": stats.telegram_raw,
            "crawl_content": stats.crawl_content,
            "llm_payload": stats.llm_payload,
            "video_transcript": stats.video_transcript,
            "interaction_text": stats.interaction_text,
            "request_content": stats.request_content,
        },
    )
    return stats


# ---------------------------------------------------------------------------
# Per-subsystem helpers — each returns rowcount (0 if TTL disabled)
# ---------------------------------------------------------------------------


async def _purge_telegram_raw(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL text_full, entities_json, telegram_raw_json.

    telegram_messages has no own timestamp; age is derived from the parent
    requests.created_at via JOIN.
    """
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(TelegramMessage)
            .where(
                TelegramMessage.id.in_(
                    select(TelegramMessage.id)
                    .join(Request, Request.id == TelegramMessage.request_id)
                    .where(
                        Request.created_at < cutoff,
                        (
                            TelegramMessage.text_full.is_not(None)
                            | TelegramMessage.entities_json.is_not(None)
                            | TelegramMessage.telegram_raw_json.is_not(None)
                        ),
                    )
                    .limit(batch)
                )
            )
            .values(text_full=None, entities_json=None, telegram_raw_json=None)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def _purge_crawl_content(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL content_markdown, content_html, raw_response_json, firecrawl_details_json,
    structured_json, metadata_json, links_json.

    crawl_results has updated_at but not created_at; use updated_at as age reference.
    """
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(CrawlResult)
            .where(
                CrawlResult.id.in_(
                    select(CrawlResult.id)
                    .where(
                        CrawlResult.updated_at < cutoff,
                        (
                            CrawlResult.content_markdown.is_not(None)
                            | CrawlResult.content_html.is_not(None)
                            | CrawlResult.raw_response_json.is_not(None)
                            | CrawlResult.firecrawl_details_json.is_not(None)
                            | CrawlResult.structured_json.is_not(None)
                            | CrawlResult.metadata_json.is_not(None)
                            | CrawlResult.links_json.is_not(None)
                        ),
                    )
                    .limit(batch)
                )
            )
            .values(
                content_markdown=None,
                content_html=None,
                raw_response_json=None,
                firecrawl_details_json=None,
                structured_json=None,
                metadata_json=None,
                links_json=None,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def _purge_llm_payload(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL request_messages_json, request_headers_json, response_text, response_json,
    openrouter_response_text, openrouter_response_json.

    Preserves: model, tokens_prompt, tokens_completion, cost_usd, latency_ms,
    status, attempt_index, attempt_trigger.
    """
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(LLMCall)
            .where(
                LLMCall.id.in_(
                    select(LLMCall.id)
                    .where(
                        LLMCall.created_at < cutoff,
                        (
                            LLMCall.request_messages_json.is_not(None)
                            | LLMCall.request_headers_json.is_not(None)
                            | LLMCall.response_text.is_not(None)
                            | LLMCall.response_json.is_not(None)
                            | LLMCall.openrouter_response_text.is_not(None)
                            | LLMCall.openrouter_response_json.is_not(None)
                        ),
                    )
                    .limit(batch)
                )
            )
            .values(
                request_messages_json=None,
                request_headers_json=None,
                response_text=None,
                response_json=None,
                openrouter_response_text=None,
                openrouter_response_json=None,
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def _purge_video_transcript(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL transcript_text in video_downloads."""
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(VideoDownload)
            .where(
                VideoDownload.id.in_(
                    select(VideoDownload.id)
                    .where(
                        VideoDownload.created_at < cutoff,
                        VideoDownload.transcript_text.is_not(None),
                    )
                    .limit(batch)
                )
            )
            .values(transcript_text=None)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def _purge_interaction_text(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL input_text in user_interactions."""
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(UserInteraction)
            .where(
                UserInteraction.id.in_(
                    select(UserInteraction.id)
                    .where(
                        UserInteraction.created_at < cutoff,
                        UserInteraction.input_text.is_not(None),
                    )
                    .limit(batch)
                )
            )
            .values(input_text=None)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0


async def _purge_request_content(
    db: Database, now: dt.datetime, days: int, batch: int
) -> int:
    """NULL content_text and error_context_json in requests."""
    if days == 0:
        return 0
    cutoff = now - dt.timedelta(days=days)
    async with db.session() as session:
        stmt = (
            update(Request)
            .where(
                Request.id.in_(
                    select(Request.id)
                    .where(
                        Request.created_at < cutoff,
                        (
                            Request.content_text.is_not(None)
                            | Request.error_context_json.is_not(None)
                        ),
                    )
                    .limit(batch)
                )
            )
            .values(content_text=None, error_context_json=None)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0
```

- [ ] **Step 3: Verify module imports cleanly**

```bash
source .venv/bin/activate
python -c "
import sys, types
# stub taskiq so we don't need broker running
for m in ('taskiq','taskiq.abc','taskiq.abc.schedule_source','taskiq.scheduler',
          'taskiq.scheduler.scheduled_task','taskiq.message','taskiq_redis'):
    sys.modules.setdefault(m, types.ModuleType(m))
import taskiq; taskiq.AsyncBroker = object; taskiq.TaskiqDepends = lambda fn, **_: None
taskiq.InMemoryBroker = type('IB', (), {})
import taskiq_redis; taskiq_redis.RedisStreamBroker = type('R', (), {})
taskiq_redis.RedisAsyncResultBackend = type('RB', (), {})
from app.tasks.purge_raw_data import PurgeStats, _purge_body
print('imports OK'); print(PurgeStats())
"
```

Expected: `imports OK` followed by `PurgeStats(telegram_raw=0, ...)`.

- [ ] **Step 4: Commit**

```bash
git add app/tasks/purge_raw_data.py
git commit -m "feat(tasks): add purge_raw_data Taskiq task with per-subsystem field nulling"
```

---

## Task 3: Scheduler Registration

**Files:**
- Modify: `app/tasks/scheduler.py`

- [ ] **Step 1: Add retention task to `_build_tasks()`**

In `app/tasks/scheduler.py`, find the `if cfg.vector_reconcile.enabled:` block (around line 98) and add after it:

```python
        if cfg.retention.enabled:
            tasks.append(
                ScheduledTask(
                    task_name="ratatoskr.data.purge",
                    cron=cfg.retention.cron,
                    labels={"job": "data_purge"},
                    args=[],
                    kwargs={},
                )
            )
```

- [ ] **Step 2: Verify scheduler test still passes**

```bash
source .venv/bin/activate
python -m pytest tests/tasks/test_schedule_builder.py -q --tb=short 2>&1 | tail -10
```

Expected: all existing schedule builder tests pass.

- [ ] **Step 3: Commit**

```bash
git add app/tasks/scheduler.py
git commit -m "feat(scheduler): register ratatoskr.data.purge daily cron"
```

---

## Task 4: Unit Tests

**Files:**
- Create: `tests/tasks/test_purge_raw_data.py`

- [ ] **Step 1: Write `tests/tasks/test_purge_raw_data.py`**

```python
"""Unit tests for app.tasks.purge_raw_data.

All DB calls are mocked — no real database connection needed.
Pattern mirrors tests/tasks/test_reconcile_vector_index.py.
"""

from __future__ import annotations

import datetime as dt
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers shared across all tests
# ---------------------------------------------------------------------------


def _stub_taskiq(monkeypatch):
    """Install minimal taskiq stubs so broker.task() decorator succeeds."""
    for mod_name in (
        "taskiq",
        "taskiq.abc",
        "taskiq.abc.schedule_source",
        "taskiq.scheduler",
        "taskiq.scheduler.scheduled_task",
        "taskiq.message",
        "taskiq_redis",
    ):
        if mod_name not in sys.modules:
            monkeypatch.setitem(sys.modules, mod_name, types.ModuleType(mod_name))

    taskiq_mod = sys.modules["taskiq"]
    taskiq_mod.AsyncBroker = object
    taskiq_mod.TaskiqDepends = lambda fn, **_kw: None
    taskiq_mod.TaskiqMiddleware = object
    taskiq_mod.InMemoryBroker = MagicMock
    taskiq_mod.TaskiqScheduler = MagicMock

    msg_mod = sys.modules["taskiq.message"]
    msg_mod.TaskiqMessage = object

    sched_task_mod = sys.modules["taskiq.scheduler.scheduled_task"]
    sched_task_mod.ScheduledTask = MagicMock

    source_mod = sys.modules["taskiq.abc.schedule_source"]
    source_mod.ScheduleSource = object

    tkr_mod = sys.modules["taskiq_redis"]
    tkr_mod.RedisStreamBroker = MagicMock
    tkr_mod.RedisAsyncResultBackend = MagicMock


def _evict_app_tasks() -> None:
    for mod in list(sys.modules):
        if mod.startswith("app.tasks"):
            sys.modules.pop(mod, None)


def _build_cfg(
    *,
    enabled: bool = True,
    batch_size: int = 100,
    telegram_raw_days: int = 7,
    crawl_content_days: int = 7,
    llm_payload_days: int = 7,
    video_transcript_days: int = 7,
    interaction_text_days: int = 7,
    request_content_days: int = 7,
) -> SimpleNamespace:
    return SimpleNamespace(
        retention=SimpleNamespace(
            enabled=enabled,
            batch_size=batch_size,
            telegram_raw_days=telegram_raw_days,
            crawl_content_days=crawl_content_days,
            llm_payload_days=llm_payload_days,
            video_transcript_days=video_transcript_days,
            interaction_text_days=interaction_text_days,
            request_content_days=request_content_days,
        )
    )


def _make_mock_db(rowcount: int = 3) -> MagicMock:
    """Return a mock Database whose session context manager returns rowcount."""
    mock_db = MagicMock()
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = rowcount
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_db.session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db.session.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_db


# ---------------------------------------------------------------------------
# Cross-cutting: enabled=False and TTL=0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_body_disabled_returns_zero_stats(monkeypatch):
    """When retention.enabled is False, _purge_body returns all-zero PurgeStats."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import PurgeStats, _purge_body

    stats = await _purge_body(_build_cfg(enabled=False), MagicMock())

    assert stats == PurgeStats()


@pytest.mark.asyncio
async def test_purge_crawl_content_ttl_zero_skips(monkeypatch):
    """days=0 causes _purge_crawl_content to return 0 without touching the DB."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_crawl_content

    mock_db = _make_mock_db(rowcount=99)
    count = await _purge_crawl_content(mock_db, dt.datetime.now(dt.timezone.utc), days=0, batch=100)

    assert count == 0
    mock_db.session.assert_not_called()


# ---------------------------------------------------------------------------
# Per-subsystem: each helper NULLs the right rows and returns rowcount
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_telegram_raw_returns_rowcount(monkeypatch):
    """_purge_telegram_raw issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_telegram_raw

    mock_db = _make_mock_db(rowcount=5)
    count = await _purge_telegram_raw(mock_db, dt.datetime.now(dt.timezone.utc), days=7, batch=100)

    assert count == 5
    mock_db.session.return_value.__aenter__.assert_called_once()
    mock_db.session.return_value.__aenter__.return_value.execute.assert_called_once()
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_crawl_content_returns_rowcount(monkeypatch):
    """_purge_crawl_content issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_crawl_content

    mock_db = _make_mock_db(rowcount=3)
    count = await _purge_crawl_content(mock_db, dt.datetime.now(dt.timezone.utc), days=7, batch=100)

    assert count == 3
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_llm_payload_returns_rowcount(monkeypatch):
    """_purge_llm_payload issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_llm_payload

    mock_db = _make_mock_db(rowcount=12)
    count = await _purge_llm_payload(mock_db, dt.datetime.now(dt.timezone.utc), days=90, batch=100)

    assert count == 12
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_video_transcript_returns_rowcount(monkeypatch):
    """_purge_video_transcript issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_video_transcript

    mock_db = _make_mock_db(rowcount=2)
    count = await _purge_video_transcript(mock_db, dt.datetime.now(dt.timezone.utc), days=30, batch=100)

    assert count == 2
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_interaction_text_returns_rowcount(monkeypatch):
    """_purge_interaction_text issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_interaction_text

    mock_db = _make_mock_db(rowcount=7)
    count = await _purge_interaction_text(mock_db, dt.datetime.now(dt.timezone.utc), days=30, batch=100)

    assert count == 7
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_purge_request_content_returns_rowcount(monkeypatch):
    """_purge_request_content issues one UPDATE and returns the affected rowcount."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_request_content

    mock_db = _make_mock_db(rowcount=4)
    count = await _purge_request_content(mock_db, dt.datetime.now(dt.timezone.utc), days=30, batch=100)

    assert count == 4
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Idempotency: rowcount=0 on second run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_crawl_content_idempotent_on_zero_rowcount(monkeypatch):
    """When rowcount is 0 (nothing left to purge), helper returns 0 cleanly."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_crawl_content

    mock_db = _make_mock_db(rowcount=0)
    count = await _purge_crawl_content(mock_db, dt.datetime.now(dt.timezone.utc), days=7, batch=100)

    assert count == 0
    # commit still called — the UPDATE ran, it just matched nothing
    mock_db.session.return_value.__aenter__.return_value.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _purge_body aggregates all subsystem counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_purge_body_aggregates_subsystem_counts(monkeypatch):
    """_purge_body sums rowcounts from all six subsystem helpers."""
    _stub_taskiq(monkeypatch)
    _evict_app_tasks()

    from app.tasks.purge_raw_data import _purge_body

    # Patch each helper with known return values
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_telegram_raw", AsyncMock(return_value=1))
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_crawl_content", AsyncMock(return_value=2))
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_llm_payload", AsyncMock(return_value=3))
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_video_transcript", AsyncMock(return_value=4))
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_interaction_text", AsyncMock(return_value=5))
    monkeypatch.setattr("app.tasks.purge_raw_data._purge_request_content", AsyncMock(return_value=6))

    stats = await _purge_body(_build_cfg(), MagicMock())

    assert stats.telegram_raw == 1
    assert stats.crawl_content == 2
    assert stats.llm_payload == 3
    assert stats.video_transcript == 4
    assert stats.interaction_text == 5
    assert stats.request_content == 6
```

- [ ] **Step 2: Run the tests**

```bash
source .venv/bin/activate
python -m pytest tests/tasks/test_purge_raw_data.py -v --tb=short 2>&1 | tail -20
```

Expected: all 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/tasks/test_purge_raw_data.py
git commit -m "test(tasks): add unit tests for purge_raw_data task"
```

---

## Task 5: Documentation

**Files:**
- Modify: `docs/reference/environment-variables.md`

- [ ] **Step 1: Add `## Data Retention` section**

Open `docs/reference/environment-variables.md` and find the `## Background Processor` section. Add the following section immediately after the Background Processor block ends:

```markdown
## Data Retention

Configures scheduled nulling of raw artifact columns (scraped HTML, LLM payloads,
Telegram message JSON, video transcripts). The summary, cost, and status columns are
never purged. A TTL of `0` disables purge for that subsystem.

| Variable | Type | Default | Description |
|---|---|---|---|
| `RETENTION_ENABLED` | bool | `true` | Master switch. Set to `false` to disable all purge runs. |
| `RETENTION_CRON` | str | `"0 3 * * *"` | UTC cron for the daily purge job (3am UTC). |
| `RETENTION_BATCH_SIZE` | int | `500` | Max rows updated per subsystem per run. Next run continues the batch. |
| `RETENTION_TELEGRAM_RAW_DAYS` | int | `30` | Days to keep `telegram_messages` raw columns (`text_full`, `entities_json`, `telegram_raw_json`). `0` = never purge. |
| `RETENTION_CRAWL_CONTENT_DAYS` | int | `7` | Days to keep `crawl_results` content columns (`content_markdown`, `content_html`, `raw_response_json`, `firecrawl_details_json`, `structured_json`, `metadata_json`, `links_json`). `0` = never purge. |
| `RETENTION_LLM_PAYLOAD_DAYS` | int | `90` | Days to keep `llm_calls` request/response columns. Cost, token, and latency fields are always preserved. `0` = never purge. |
| `RETENTION_VIDEO_TRANSCRIPT_DAYS` | int | `30` | Days to keep `video_downloads.transcript_text`. `0` = never purge. |
| `RETENTION_INTERACTION_TEXT_DAYS` | int | `30` | Days to keep `user_interactions.input_text`. `0` = never purge. |
| `RETENTION_REQUEST_CONTENT_DAYS` | int | `30` | Days to keep `requests.content_text` and `requests.error_context_json`. `0` = never purge. |
```

- [ ] **Step 2: Commit**

```bash
git add docs/reference/environment-variables.md
git commit -m "docs: document RETENTION_* env vars for raw-data purge"
```

---

## Verification

After all tasks are complete:

```bash
source .venv/bin/activate
python -m pytest tests/tasks/test_purge_raw_data.py tests/tasks/test_schedule_builder.py -v --tb=short 2>&1 | tail -15
```

Expected: all tests pass with no failures or warnings.
