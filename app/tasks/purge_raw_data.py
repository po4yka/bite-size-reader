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
# 10 minutes: covers 6 subsystems x batch_size=500 rows each with room to spare.
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
    now = dt.datetime.now(dt.UTC)

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
