from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.adapters.telegram import telegram_client as telegram_client_module
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import generate_correlation_id, setup_json_logging
from app.core.time_utils import UTC
from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)

try:
    from pyrogram import Client, filters
except ImportError:
    Client = object
    filters = None

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


# ...
@dataclass
class TelegramBot:
    """Refactored Telegram bot using modular components."""

    cfg: AppConfig
    db: DatabaseSessionManager

    def __post_init__(self) -> None:
        """Initialize bot components using factory pattern."""
        setup_json_logging(self.cfg.runtime.log_level)
        logger.info(
            "bot_init",
            extra={
                "db_path": self.cfg.runtime.db_path,
                "log_level": self.cfg.runtime.log_level,
            },
        )

        # Reflect monkeypatches from tests into the telegram_client module so
        # that no real Pyrogram client is constructed.
        setattr(telegram_client_module, "Client", Client)  # noqa: B010
        setattr(telegram_client_module, "filters", filters)  # noqa: B010
        if Client is object:
            telegram_client_module.PYROGRAM_AVAILABLE = False

        # Initialize semaphore for concurrency control
        self._ext_sem_size = max(1, self.cfg.runtime.max_concurrent_calls)
        self._ext_sem_obj: asyncio.Semaphore | None = None

        self.audit_repo = SqliteAuditLogRepositoryAdapter(self.db)

        # Create external clients using factory
        from app.adapters.telegram.bot_factory import BotFactory

        clients = BotFactory.create_external_clients(
            cfg=self.cfg,
            audit_func=self._audit,
        )
        self._firecrawl = clients.firecrawl
        self._llm_client = clients.llm_client

        # Create all bot components using factory
        components = BotFactory.create_components(
            cfg=self.cfg,
            db=self.db,
            clients=clients,
            audit_func=self._audit,
            safe_reply_func=self._safe_reply,
            reply_json_func=self._reply_json,
            sem_func=self._sem,
        )

        # Assign components to instance attributes
        self.telegram_client = components.telegram_client
        self.response_formatter = components.response_formatter
        self.url_processor = components.url_processor
        self.forward_processor = components.forward_processor
        self.message_handler = components.message_handler
        self.topic_searcher = components.topic_searcher
        self.local_searcher = components.local_searcher
        self.embedding_service = components.embedding_service
        # Backward-compat alias for legacy usages
        self.vector_search_service = components.chroma_vector_search_service
        self.query_expansion_service = components.query_expansion_service
        self.hybrid_search_service = components.hybrid_search_service
        self.vector_store = components.vector_store
        self._container = components.container

        # Point handlers directly at the real url_processor
        self.message_handler.command_processor.url_processor = self.url_processor
        self.message_handler.url_handler.url_processor = self.url_processor
        self.message_handler.url_processor = self.url_processor

        # Expose in-memory state containers for unit tests
        self._awaiting_url_users = self.message_handler.url_handler._awaiting_url_users
        self._pending_multi_links = self.message_handler.url_handler._pending_multi_links

        # Sync dependencies (in case they were updated)
        self._sync_client_dependencies()

        # Initialize scheduler for background tasks (e.g., Karakeep sync)
        from app.services.scheduler import SchedulerService

        self._scheduler = SchedulerService(cfg=self.cfg, db=self.db)

    def _sem(self) -> asyncio.Semaphore:
        """Lazy-create a semaphore when an event loop is running.

        This avoids creating an asyncio.Semaphore at import/constructor time in tests
        that instantiate the bot without a running event loop.
        """
        if self._ext_sem_obj is None:
            self._ext_sem_obj = asyncio.Semaphore(self._ext_sem_size)
        return self._ext_sem_obj

    async def start(self) -> None:
        """Start the bot."""
        backup_enabled, interval, retention, backup_dir = self._get_backup_settings()
        if backup_enabled and interval > 0:
            self._backup_task = asyncio.create_task(
                self._run_backup_loop(interval, retention, backup_dir),
                name="db_backup_loop",
            )
        elif backup_enabled:
            logger.warning(
                "db_backup_disabled_invalid_interval",
                extra={"interval_minutes": interval},
            )

        # Start rate limiter cleanup task (runs every 5 minutes)
        self._rate_limiter_cleanup_task = asyncio.create_task(
            self._run_rate_limiter_cleanup_loop(),
            name="rate_limiter_cleanup_loop",
        )

        # Start background scheduler for periodic tasks (e.g., Karakeep sync)
        await self._scheduler.start()

        try:
            await self.telegram_client.start(
                self.message_handler.handle_message,
                self.message_handler.handle_callback_query,
            )
        finally:
            # Stop scheduler gracefully
            await self._scheduler.stop()

            if hasattr(self, "_backup_task") and self._backup_task is not None:
                self._backup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._backup_task

            if (
                hasattr(self, "_rate_limiter_cleanup_task")
                and self._rate_limiter_cleanup_task is not None
            ):
                self._rate_limiter_cleanup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._rate_limiter_cleanup_task

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper (background async)."""
        if not hasattr(self, "audit_repo"):
            return

        async def _do_audit() -> None:
            try:
                await self.audit_repo.async_insert_audit_log(
                    log_level=level, event_type=event, details=details
                )
            except Exception as e:
                logger.warning("audit_persist_failed", extra={"error": str(e), "event": event})

        try:
            task = asyncio.create_task(_do_audit())
            # Keep a set of strong references to tasks to avoid them being GC'd
            if not hasattr(self, "_audit_tasks"):
                self._audit_tasks: set[asyncio.Task] = set()
            self._audit_tasks.add(task)
            task.add_done_callback(self._audit_tasks.discard)
        except RuntimeError:
            pass

    def _mask_path(self, path: str) -> str:
        """Mask home directory in paths for logging."""
        try:
            return str(path).replace(str(Path.home()), "~")
        except Exception:
            return path

    def _sync_client_dependencies(self) -> None:
        """Ensure helper components reference the active external clients."""
        firecrawl = getattr(self, "_firecrawl", None)
        llm_client = getattr(self, "_llm_client", None)

        if hasattr(self, "url_processor"):
            extractor = getattr(self.url_processor, "content_extractor", None)
            if extractor is not None:
                extractor.firecrawl = firecrawl

            chunker = getattr(self.url_processor, "content_chunker", None)
            if chunker is not None:
                chunker.openrouter = llm_client

            summarizer = getattr(self.url_processor, "llm_summarizer", None)
            if summarizer is not None:
                summarizer.openrouter = llm_client
                workflow = getattr(summarizer, "_workflow", None)
                if workflow is not None:
                    workflow.openrouter = llm_client

        if hasattr(self, "forward_processor"):
            forward_summarizer = getattr(self.forward_processor, "summarizer", None)
            if forward_summarizer is not None:
                forward_summarizer.openrouter = llm_client

    def _get_backup_settings(self) -> tuple[bool, int, int, str | None]:
        """Return sanitized backup configuration values."""
        runtime = getattr(self.cfg, "runtime", None)
        if runtime is None:
            return False, 0, 0, None

        enabled_raw = getattr(runtime, "db_backup_enabled", False)
        enabled = bool(enabled_raw) if isinstance(enabled_raw, bool | int) else False

        interval_raw = getattr(runtime, "db_backup_interval_minutes", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        interval = max(0, interval)

        retention_raw = getattr(runtime, "db_backup_retention", 0)
        retention = retention_raw if isinstance(retention_raw, int) else 0
        retention = max(retention, 0)

        backup_dir_raw = getattr(runtime, "db_backup_dir", None)
        backup_dir = (
            backup_dir_raw.strip()
            if isinstance(backup_dir_raw, str) and backup_dir_raw.strip()
            else None
        )

        return enabled, interval, retention, backup_dir

    async def _run_backup_loop(
        self, interval_minutes: int, retention: int, backup_dir: str | None
    ) -> None:
        """Periodically create database backups until cancelled.

        Implements failure tracking with alerting after consecutive failures.
        """
        if interval_minutes <= 0:
            return

        backup_directory = self._resolve_backup_dir(backup_dir)
        logger.info(
            "db_backup_loop_started",
            extra={
                "interval_minutes": interval_minutes,
                "retention": retention,
                "backup_dir": self._mask_path(str(backup_directory)),
            },
        )

        # Failure tracking
        consecutive_failures = 0
        max_consecutive_failures = 5
        last_success_time = None

        try:
            while True:
                try:
                    await self._create_database_backup(backup_directory, retention)
                    # Reset failure counter on success
                    if consecutive_failures > 0:
                        logger.info(
                            "db_backup_recovered",
                            extra={
                                "consecutive_failures": consecutive_failures,
                                "recovery_time": datetime.now(UTC).isoformat(),
                            },
                        )
                    consecutive_failures = 0
                    last_success_time = datetime.now(UTC)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    consecutive_failures += 1
                    logger.exception(
                        "db_backup_iteration_failed",
                        extra={
                            "error": str(exc),
                            "consecutive_failures": consecutive_failures,
                            "last_success": (
                                last_success_time.isoformat() if last_success_time else "never"
                            ),
                        },
                    )

                    # Alert on consecutive failures
                    if consecutive_failures >= max_consecutive_failures:
                        logger.critical(
                            "db_backup_critical_failure",
                            extra={
                                "consecutive_failures": consecutive_failures,
                                "max_failures": max_consecutive_failures,
                                "last_success": (
                                    last_success_time.isoformat() if last_success_time else "never"
                                ),
                                "action_required": "Manual intervention required - backups failing",
                            },
                        )
                        # Audit log for critical failures
                        with contextlib.suppress(Exception):
                            self._audit(
                                "CRITICAL",
                                "db_backup_critical_failure",
                                {
                                    "consecutive_failures": consecutive_failures,
                                    "last_success": (
                                        last_success_time.isoformat()
                                        if last_success_time
                                        else "never"
                                    ),
                                },
                            )

                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            logger.info("db_backup_loop_cancelled")
            raise

    async def _create_database_backup(self, backup_directory: Path, retention: int) -> None:
        """Create a single backup and prune according to retention settings."""
        db_path = getattr(self.db, "path", "")
        if db_path == ":memory:":
            logger.debug("db_backup_skipped_in_memory")
            return

        base_path = Path(db_path)
        suffix = base_path.suffix or ".db"
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup_file = backup_directory / f"{base_path.stem}-{timestamp}{suffix}"

        try:
            created_path = await asyncio.to_thread(self.db.create_backup_copy, str(backup_file))
        except FileNotFoundError as exc:
            logger.warning("db_backup_source_missing", extra={"error": str(exc)})
            return
        except ValueError as exc:
            logger.debug("db_backup_not_applicable", extra={"reason": str(exc)})
            return
        except Exception as exc:
            logger.exception("db_backup_failed", extra={"error": str(exc)})
            return

        try:
            self._cleanup_old_backups(backup_directory, base_path.stem, suffix, retention)
        except Exception as exc:
            logger.warning("db_backup_cleanup_failed", extra={"error": str(exc)})

        logger.info(
            "db_backup_created",
            extra={"backup_path": self._mask_path(str(created_path))},
        )

    def _resolve_backup_dir(self, override: str | None) -> Path:
        """Determine the directory to store backups in."""
        if override:
            path = Path(override).expanduser()
        else:
            base = Path(self.db.path)
            parent = base.parent if base.parent != Path() else Path()
            path = parent / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _cleanup_old_backups(
        self, backup_directory: Path, base_name: str, suffix: str, retention: int
    ) -> None:
        """Remove older backup files beyond the retention limit."""
        if retention <= 0:
            return

        try:
            candidates = sorted(
                (
                    file
                    for file in backup_directory.iterdir()
                    if file.is_file()
                    and file.name.startswith(f"{base_name}-")
                    and file.suffix == suffix
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning(
                "db_backup_list_failed",
                extra={"backup_dir": self._mask_path(str(backup_directory)), "error": str(exc)},
            )
            return

        for obsolete in candidates[retention:]:
            try:
                obsolete.unlink()
            except OSError as exc:
                logger.warning(
                    "db_backup_remove_failed",
                    extra={"backup_path": self._mask_path(str(obsolete)), "error": str(exc)},
                )

    async def _run_rate_limiter_cleanup_loop(self, interval_minutes: int = 5) -> None:
        """Periodically clean up expired rate limiter entries to prevent memory leaks.

        Args:
            interval_minutes: How often to run cleanup (default: 5 minutes)
        """
        logger.info(
            "rate_limiter_cleanup_loop_started",
            extra={"interval_minutes": interval_minutes},
        )
        try:
            while True:
                await asyncio.sleep(interval_minutes * 60)
                try:
                    cleaned = await self.message_handler.message_router.cleanup_rate_limiter()
                    if cleaned > 0:
                        logger.debug(
                            "rate_limiter_cleanup_completed",
                            extra={"users_cleaned": cleaned},
                        )
                except Exception as exc:
                    logger.warning(
                        "rate_limiter_cleanup_error",
                        extra={"error": str(exc)},
                    )
                # Also clean up expired URL handler state
                try:
                    if hasattr(self.message_handler, "url_handler"):
                        url_cleaned = await self.message_handler.url_handler.cleanup_expired_state()
                        if url_cleaned > 0:
                            logger.debug(
                                "url_handler_state_cleanup_completed",
                                extra={"entries_cleaned": url_cleaned},
                            )
                except Exception as exc:
                    logger.warning(
                        "url_handler_state_cleanup_error",
                        extra={"error": str(exc)},
                    )
        except asyncio.CancelledError:
            logger.info("rate_limiter_cleanup_loop_cancelled")
            raise

    # ---- Compatibility helpers expected by tests (typed stubs) ----
    async def _safe_reply(
        self,
        message: Any,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        **extra_kwargs: Any,
    ) -> None:
        """Safely reply to a message (legacy-compatible helper)."""
        _rt = getattr(getattr(self, "cfg", None), "runtime", None)
        _timeout: float = getattr(_rt, "telegram_reply_timeout_sec", 30.0)
        try:
            if hasattr(message, "reply_text"):
                kwargs: dict[str, Any] = {}
                if parse_mode is not None:
                    kwargs["parse_mode"] = parse_mode
                if reply_markup is not None:
                    kwargs["reply_markup"] = reply_markup
                if extra_kwargs:
                    kwargs.update(extra_kwargs)
                await asyncio.wait_for(message.reply_text(text, **kwargs), timeout=_timeout)
        except TimeoutError:
            logger.warning(
                "telegram_reply_timeout",
                extra={"method": "_safe_reply", "timeout_sec": _timeout},
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            # Swallow in tests; production response path logs and continues.

    async def _reply_json(
        self,
        message: Any,
        payload: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Reply with JSON payload as a document with descriptive filename.

        Falls back to plain text if document upload fails.
        """
        _rt = getattr(getattr(self, "cfg", None), "runtime", None)
        _timeout: float = getattr(_rt, "telegram_reply_timeout_sec", 30.0)
        try:
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)

            # Build a descriptive filename based on SEO keywords or TL;DR
            def _slugify(text: str, max_len: int = 60) -> str:
                import re as _re

                s = text.strip().lower()
                s = _re.sub(r"[^\w\-\s]", "", s)
                s = _re.sub(r"[\s_]+", "-", s)
                s = _re.sub(r"-+", "-", s).strip("-")
                if len(s) > max_len:
                    s = s[:max_len].rstrip("-")
                return s or "summary"

            base: str | None = None
            seo = payload.get("seo_keywords") or []
            if isinstance(seo, list) and seo:
                base = "-".join(_slugify(str(x)) for x in seo[:3] if str(x).strip())
            if not base:
                tl = str(payload.get("summary_250", "")).strip()
                if tl:
                    import re as _re

                    words = _re.findall(r"\w+", tl)[:6]
                    base = _slugify("-".join(words))
            if not base:
                base = "summary"
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            filename = f"{base}-{ts}.json"

            if hasattr(message, "reply_document"):
                bio = io.BytesIO(pretty.encode("utf-8"))
                bio.name = filename
                await asyncio.wait_for(
                    message.reply_document(bio, caption="📊 Full Summary JSON attached"),
                    timeout=_timeout,
                )
                return

            # Fallback to text
            if hasattr(message, "reply_text"):
                await asyncio.wait_for(
                    message.reply_text(f"```json\n{pretty}\n```"), timeout=_timeout
                )
        except TimeoutError:
            logger.warning(
                "telegram_reply_timeout",
                extra={"method": "_reply_json", "timeout_sec": _timeout},
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            try:
                text = json.dumps(payload, ensure_ascii=False)
                if hasattr(message, "reply_text"):
                    await asyncio.wait_for(message.reply_text(text), timeout=_timeout)
            except TimeoutError:
                logger.warning(
                    "telegram_reply_timeout",
                    extra={"method": "_reply_json_fallback", "timeout_sec": _timeout},
                )
            except Exception as inner_exc:
                raise_if_cancelled(inner_exc)
        _ = metadata

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> None:
        """Adapter used by command/url handlers to process URL flows."""
        await self._handle_url_flow(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=silent,
        )

    async def _handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> None:
        """Process a URL message via the URL processor pipeline."""
        await self.url_processor.handle_url_flow(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=silent,
        )

    async def _handle_forward_flow(
        self,
        message: Any,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Process a forwarded message via the forward processor pipeline."""
        cid = correlation_id or generate_correlation_id()
        await self.forward_processor.handle_forward_flow(
            message, correlation_id=cid, interaction_id=interaction_id
        )

    async def handle_forward_flow(
        self,
        message: Any,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Compatibility shim mirroring the URL flow adapter."""
        await self._handle_forward_flow(
            message, correlation_id=correlation_id, interaction_id=interaction_id
        )

    async def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist a Telegram message snapshot for legacy tests."""
        await self.url_processor.message_persistence.persist_message_snapshot(request_id, message)

    async def _on_message(self, message: Any) -> None:
        """Entry point used by tests; delegate to message handler."""
        uid = getattr(getattr(message, "from_user", None), "id", None)
        logger.info("handling_message uid=%s", uid, extra={"uid": uid})
        await self.message_handler.handle_message(message)

    def __setattr__(self, name: str, value: Any) -> None:
        """Track client updates so helper components stay in sync."""
        super().__setattr__(name, value)
        if name in {"_firecrawl", "_openrouter"}:
            # During ``__init__`` the helper attributes may not exist yet.
            if hasattr(self, "_sync_client_dependencies"):
                self._sync_client_dependencies()
        if name in {"_safe_reply", "_reply_json"} and hasattr(self, "response_formatter"):
            if name == "_safe_reply":
                self.response_formatter._safe_reply_func = value
            else:
                self.response_formatter._reply_json_func = value
