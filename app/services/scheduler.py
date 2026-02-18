"""Background scheduler for periodic tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.time_utils import UTC

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages background scheduled tasks like Karakeep sync."""

    def __init__(self, cfg: AppConfig, db: DatabaseSessionManager) -> None:
        """Initialize scheduler service.

        Args:
            cfg: Application configuration
            db: DatabaseSessionManager instance
        """
        self.cfg = cfg
        self.db = db
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    async def start(self) -> None:
        """Start the scheduler with configured jobs."""
        if self._started:
            logger.warning("scheduler_already_started")
            return

        self._scheduler = AsyncIOScheduler()

        # Add Karakeep sync job if enabled
        if (
            self.cfg.karakeep.enabled
            and self.cfg.karakeep.api_key
            and self.cfg.karakeep.auto_sync_enabled
        ):
            self._scheduler.add_job(
                self._run_karakeep_sync,
                trigger=IntervalTrigger(hours=self.cfg.karakeep.sync_interval_hours),
                id="karakeep_sync",
                name="Karakeep Bookmark Sync",
                replace_existing=True,
                max_instances=1,  # Prevent overlapping runs
            )
            logger.info(
                "scheduler_karakeep_job_added",
                extra={
                    "job_id": "karakeep_sync",
                    "interval_hours": self.cfg.karakeep.sync_interval_hours,
                },
            )
        else:
            logger.info(
                "scheduler_karakeep_job_skipped",
                extra={
                    "enabled": self.cfg.karakeep.enabled,
                    "has_api_key": bool(self.cfg.karakeep.api_key),
                    "auto_sync_enabled": self.cfg.karakeep.auto_sync_enabled,
                },
            )

        # Add channel digest jobs if enabled (one per configured time)
        if self.cfg.digest.enabled:
            for idx, time_str in enumerate(self.cfg.digest.digest_times):
                hour, minute = map(int, time_str.split(":"))
                job_id = f"channel_digest_{idx}"
                self._scheduler.add_job(
                    self._run_channel_digest,
                    trigger=CronTrigger(
                        hour=hour, minute=minute, timezone=self.cfg.digest.timezone
                    ),
                    id=job_id,
                    name=f"Channel Digest Delivery ({time_str})",
                    replace_existing=True,
                    max_instances=1,
                )
                logger.info(
                    "scheduler_digest_job_added",
                    extra={
                        "job_id": job_id,
                        "time": time_str,
                        "timezone": self.cfg.digest.timezone,
                    },
                )
        else:
            logger.info("scheduler_digest_job_skipped", extra={"enabled": False})

        self._scheduler.start()
        self._started = True
        logger.info("scheduler_started")

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
            self._started = False
            logger.info("scheduler_stopped")

    async def _run_karakeep_sync(self) -> None:
        """Execute scheduled Karakeep sync."""
        from app.adapters.karakeep import KarakeepSyncService
        from app.infrastructure.persistence.sqlite.repositories.karakeep_sync_repository import (
            SqliteKarakeepSyncRepositoryAdapter,
        )

        correlation_id = f"scheduled_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        logger.info("scheduled_karakeep_sync_starting", extra={"cid": correlation_id})

        try:
            karakeep_repo = SqliteKarakeepSyncRepositoryAdapter(self.db)
            service = KarakeepSyncService(
                api_url=self.cfg.karakeep.api_url,
                api_key=self.cfg.karakeep.api_key,
                sync_tag=self.cfg.karakeep.sync_tag,
                repository=karakeep_repo,
            )

            # Get default user ID from allowed users
            user_id = (
                self.cfg.telegram.allowed_user_ids[0]
                if self.cfg.telegram.allowed_user_ids
                else None
            )

            if user_id is None:
                logger.warning(
                    "scheduled_karakeep_sync_no_user_id",
                    extra={"cid": correlation_id},
                )
                return

            result = await service.run_full_sync(user_id=user_id)

            total_errors = len(result.bsr_to_karakeep.errors) + len(result.karakeep_to_bsr.errors)
            logger.info(
                "scheduled_karakeep_sync_complete",
                extra={
                    "cid": correlation_id,
                    "bsr_to_karakeep_synced": result.bsr_to_karakeep.items_synced,
                    "bsr_to_karakeep_skipped": result.bsr_to_karakeep.items_skipped,
                    "bsr_to_karakeep_failed": result.bsr_to_karakeep.items_failed,
                    "karakeep_to_bsr_synced": result.karakeep_to_bsr.items_synced,
                    "karakeep_to_bsr_skipped": result.karakeep_to_bsr.items_skipped,
                    "karakeep_to_bsr_failed": result.karakeep_to_bsr.items_failed,
                    "duration_seconds": result.total_duration_seconds,
                    "errors": total_errors,
                },
            )

        except Exception as e:
            logger.exception(
                "scheduled_karakeep_sync_failed",
                extra={"cid": correlation_id, "error": str(e)},
            )

    async def _run_channel_digest(self) -> None:
        """Execute scheduled channel digest delivery for all subscribed users."""
        from pathlib import Path

        from app.adapters.digest.analyzer import DigestAnalyzer
        from app.adapters.digest.channel_reader import ChannelReader
        from app.adapters.digest.digest_service import DigestService
        from app.adapters.digest.formatter import DigestFormatter
        from app.adapters.digest.userbot_client import UserbotClient

        correlation_id = f"digest_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        logger.info("scheduled_digest_starting", extra={"cid": correlation_id})

        userbot: UserbotClient | None = None
        try:
            # Initialize userbot
            session_dir = Path("/data")
            userbot = UserbotClient(self.cfg, session_dir)
            await userbot.start()

            # Build LLM client (reuse OpenRouter)
            from app.adapters.openrouter.openrouter_client import OpenRouterClient

            llm_client = OpenRouterClient(
                api_key=self.cfg.openrouter.api_key,
                model=self.cfg.openrouter.model,
                fallback_models=self.cfg.openrouter.fallback_models,
            )

            reader = ChannelReader(self.cfg, userbot)
            analyzer = DigestAnalyzer(self.cfg, llm_client)
            formatter = DigestFormatter()

            # Create a send function using the bot (not the userbot)
            # The bot client is not available here; use pyrogram bot directly
            from pyrogram import Client as PyroClient

            bot = PyroClient(
                name="digest_bot_sender",
                api_id=self.cfg.telegram.api_id,
                api_hash=self.cfg.telegram.api_hash,
                bot_token=self.cfg.telegram.bot_token,
                in_memory=True,
            )

            async with bot:

                async def send_message(
                    user_id: int, text: str, reply_markup: object = None
                ) -> None:
                    await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

                service = DigestService(
                    cfg=self.cfg,
                    reader=reader,
                    analyzer=analyzer,
                    formatter=formatter,
                    send_message_func=send_message,
                )

                # Deliver to all users with subscriptions
                user_ids = service.get_users_with_subscriptions()
                logger.info(
                    "scheduled_digest_users",
                    extra={"cid": correlation_id, "count": len(user_ids)},
                )

                for uid in user_ids:
                    try:
                        result = await service.generate_digest(
                            user_id=uid,
                            correlation_id=f"{correlation_id}_u{uid}",
                            digest_type="scheduled",
                            lang="ru",
                        )
                        logger.info(
                            "scheduled_digest_user_complete",
                            extra={
                                "cid": correlation_id,
                                "uid": uid,
                                "posts": result.post_count,
                                "errors": len(result.errors),
                            },
                        )
                    except Exception as e:
                        logger.exception(
                            "scheduled_digest_user_failed",
                            extra={"cid": correlation_id, "uid": uid, "error": str(e)},
                        )

            await llm_client.aclose()

        except Exception as e:
            logger.exception(
                "scheduled_digest_failed",
                extra={"cid": correlation_id, "error": str(e)},
            )
        finally:
            if userbot:
                await userbot.stop()

    def get_next_run_time(self, job_id: str) -> datetime | None:
        """Get next scheduled run time for a job.

        Args:
            job_id: Job identifier (e.g., "karakeep_sync")

        Returns:
            Next run time or None if job doesn't exist or scheduler not started
        """
        if not self._scheduler or not self._started:
            return None
        job = self._scheduler.get_job(job_id)
        return job.next_run_time if job else None

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._started and self._scheduler is not None
