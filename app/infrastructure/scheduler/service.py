"""Background scheduler for periodic tasks."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


class SchedulerService:
    """Manages background scheduled tasks."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        *,
        deps: Any,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self._deps = deps
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False

    def start(self) -> None:
        """Start the scheduler with configured jobs."""
        if self._started:
            logger.warning("scheduler_already_started")
            return

        self._scheduler = AsyncIOScheduler()

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

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
            self._started = False
            logger.info("scheduler_stopped")

    async def _run_channel_digest(self) -> None:
        """Execute scheduled channel digest delivery for all subscribed users."""
        correlation_id = f"digest_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        logger.info("scheduled_digest_starting", extra={"cid": correlation_id})

        userbot: Any | None = None
        llm_client: Any | None = None
        try:
            userbot = self._deps.digest_userbot_factory()
            await userbot.start()

            llm_client = self._deps.digest_llm_factory()
            bot = self._deps.digest_bot_client_factory()

            async with bot:

                async def send_message(user_id: int, text: str, reply_markup: Any = None) -> None:
                    await bot.send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

                service = self._deps.digest_service_factory(
                    userbot,
                    llm_client,
                    send_message,
                )

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
                    except Exception as exc:
                        logger.exception(
                            "scheduled_digest_user_failed",
                            extra={"cid": correlation_id, "uid": uid, "error": str(exc)},
                        )

        except Exception as exc:
            logger.exception(
                "scheduled_digest_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
        finally:
            if llm_client is not None:
                await llm_client.aclose()
            if userbot:
                await userbot.stop()

    def get_next_run_time(self, job_id: str) -> datetime | None:
        """Get next scheduled run time for a job."""
        if not self._scheduler or not self._started:
            return None
        job = self._scheduler.get_job(job_id)
        return job.next_run_time if job else None

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._started and self._scheduler is not None
