# ruff: noqa: E501
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.telegram import telegram_client as telegram_client_module
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.telegram.telegram_client import TelegramClient
from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id, setup_json_logging
from app.db.database import Database

logger = logging.getLogger(__name__)

# Expose pyrogram compatibility shims for test monkeypatching. Tests set
# ``Client``/``filters`` on this module to avoid importing real Pyrogram
# objects. We forward those assignments to the telegram_client module inside
# ``__post_init__``.
Client: Any = getattr(telegram_client_module, "Client", object)
filters: Any = getattr(telegram_client_module, "filters", None)


@dataclass
class TelegramBot:
    """Refactored Telegram bot using modular components."""

    cfg: AppConfig
    db: Database

    def __post_init__(self) -> None:
        """Initialize bot components."""
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
        setattr(telegram_client_module, "Client", Client)
        setattr(telegram_client_module, "filters", filters)
        if Client is object:
            telegram_client_module.PYROGRAM_AVAILABLE = False

        # Initialize external clients
        self._firecrawl = FirecrawlClient(
            api_key=self.cfg.firecrawl.api_key,
            timeout_sec=self.cfg.runtime.request_timeout_sec,
            audit=self._audit,
            debug_payloads=self.cfg.runtime.debug_payloads,
            log_truncate_length=self.cfg.runtime.log_truncate_length,
            # Connection pooling configuration
            max_connections=self.cfg.firecrawl.max_connections,
            max_keepalive_connections=self.cfg.firecrawl.max_keepalive_connections,
            keepalive_expiry=self.cfg.firecrawl.keepalive_expiry,
            credit_warning_threshold=self.cfg.firecrawl.credit_warning_threshold,
            credit_critical_threshold=self.cfg.firecrawl.credit_critical_threshold,
        )

        # Enhanced OpenRouter client with structured output support
        self._openrouter = OpenRouterClient(
            api_key=self.cfg.openrouter.api_key,
            model=self.cfg.openrouter.model,
            fallback_models=list(self.cfg.openrouter.fallback_models),
            http_referer=self.cfg.openrouter.http_referer,
            x_title=self.cfg.openrouter.x_title,
            timeout_sec=self.cfg.runtime.request_timeout_sec,
            audit=self._audit,
            debug_payloads=self.cfg.runtime.debug_payloads,
            provider_order=list(self.cfg.openrouter.provider_order),
            enable_stats=self.cfg.openrouter.enable_stats,
            log_truncate_length=self.cfg.runtime.log_truncate_length,
            # Structured output configuration
            enable_structured_outputs=self.cfg.openrouter.enable_structured_outputs,
            structured_output_mode=self.cfg.openrouter.structured_output_mode,
            require_parameters=self.cfg.openrouter.require_parameters,
            auto_fallback_structured=self.cfg.openrouter.auto_fallback_structured,
        )

        # Initialize semaphore for concurrency control
        max_conc = int(os.getenv("MAX_CONCURRENT_CALLS", "4"))
        self._ext_sem_size = max(1, max_conc)
        self._ext_sem_obj: asyncio.Semaphore | None = None

        # Initialize modular components
        self.response_formatter = ResponseFormatter(
            safe_reply_func=self._safe_reply,
            reply_json_func=self._reply_json,
            # telegram_client will be set later after initialization
        )

        self.url_processor = URLProcessor(
            cfg=self.cfg,
            db=self.db,
            firecrawl=self._firecrawl,
            openrouter=self._openrouter,
            response_formatter=self.response_formatter,
            audit_func=self._audit,
            sem=self._sem,
        )

        self.forward_processor = ForwardProcessor(
            cfg=self.cfg,
            db=self.db,
            openrouter=self._openrouter,
            response_formatter=self.response_formatter,
            audit_func=self._audit,
            sem=self._sem,
        )

        self.message_handler = MessageHandler(
            cfg=self.cfg,
            db=self.db,
            response_formatter=self.response_formatter,
            url_processor=self.url_processor,
            forward_processor=self.forward_processor,
        )

        # Route URL handling via the bot instance so legacy tests overriding
        # ``_handle_url_flow`` keep working.
        self.message_handler.command_processor.url_processor = cast(URLProcessor, self)
        self.message_handler.url_handler.url_processor = cast(URLProcessor, self)

        # Expose in-memory state containers for unit tests
        self._awaiting_url_users = self.message_handler.url_handler._awaiting_url_users
        self._pending_multi_links = self.message_handler.url_handler._pending_multi_links

        self.telegram_client = TelegramClient(cfg=self.cfg)
        self._sync_client_dependencies()

        # Set telegram client on response formatter for message editing
        self.response_formatter._telegram_client = self.telegram_client

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
        backup_task: asyncio.Task[None] | None = None
        if backup_enabled and interval > 0:
            backup_task = asyncio.create_task(
                self._run_backup_loop(interval, retention, backup_dir),
                name="db_backup_loop",
            )
        elif backup_enabled:
            logger.warning(
                "db_backup_disabled_invalid_interval",
                extra={"interval_minutes": interval},
            )

        try:
            await self.telegram_client.start(self.message_handler.handle_message)
        finally:
            if backup_task is not None:
                backup_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await backup_task

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper."""
        try:
            self.db.insert_audit_log(level=level, event=event, details_json=details)
        except Exception as e:  # noqa: BLE001
            logger.error("audit_persist_failed", extra={"error": str(e), "event": event})

    def _sync_client_dependencies(self) -> None:
        """Ensure helper components reference the active external clients."""
        firecrawl = getattr(self, "_firecrawl", None)
        openrouter = getattr(self, "_openrouter", None)

        if hasattr(self, "url_processor"):
            extractor = getattr(self.url_processor, "content_extractor", None)
            if extractor is not None:
                extractor.firecrawl = firecrawl

            chunker = getattr(self.url_processor, "content_chunker", None)
            if chunker is not None:
                chunker.openrouter = openrouter

            summarizer = getattr(self.url_processor, "llm_summarizer", None)
            if summarizer is not None:
                summarizer.openrouter = openrouter
                workflow = getattr(summarizer, "_workflow", None)
                if workflow is not None:
                    workflow.openrouter = openrouter

        if hasattr(self, "forward_processor"):
            forward_summarizer = getattr(self.forward_processor, "summarizer", None)
            if forward_summarizer is not None:
                forward_summarizer.openrouter = openrouter

    def _get_backup_settings(self) -> tuple[bool, int, int, str | None]:
        """Return sanitized backup configuration values."""

        runtime = getattr(self.cfg, "runtime", None)
        if runtime is None:
            return False, 0, 0, None

        enabled_raw = getattr(runtime, "db_backup_enabled", False)
        enabled = bool(enabled_raw) if isinstance(enabled_raw, bool | int) else False

        interval_raw = getattr(runtime, "db_backup_interval_minutes", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        if interval <= 0:
            interval = 0

        retention_raw = getattr(runtime, "db_backup_retention", 0)
        retention = retention_raw if isinstance(retention_raw, int) else 0
        if retention < 0:
            retention = 0

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
        """Periodically create database backups until cancelled."""

        if interval_minutes <= 0:
            return

        backup_directory = self._resolve_backup_dir(backup_dir)
        logger.info(
            "db_backup_loop_started",
            extra={
                "interval_minutes": interval_minutes,
                "retention": retention,
                "backup_dir": self.db._mask_path(str(backup_directory)),
            },
        )

        try:
            while True:
                try:
                    await self._create_database_backup(backup_directory, retention)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.error("db_backup_iteration_failed", extra={"error": str(exc)})

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
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        backup_file = backup_directory / f"{base_path.stem}-{timestamp}{suffix}"

        try:
            created_path = await asyncio.to_thread(self.db.create_backup_copy, str(backup_file))
        except FileNotFoundError as exc:
            logger.warning("db_backup_source_missing", extra={"error": str(exc)})
            return
        except ValueError as exc:
            logger.debug("db_backup_not_applicable", extra={"reason": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            logger.error("db_backup_failed", extra={"error": str(exc)})
            return

        try:
            self._cleanup_old_backups(backup_directory, base_path.stem, suffix, retention)
        except Exception as exc:  # noqa: BLE001
            logger.warning("db_backup_cleanup_failed", extra={"error": str(exc)})

        logger.info(
            "db_backup_created",
            extra={"backup_path": self.db._mask_path(str(created_path))},
        )

    def _resolve_backup_dir(self, override: str | None) -> Path:
        """Determine the directory to store backups in."""

        if override:
            path = Path(override).expanduser()
        else:
            base = Path(self.db.path)
            parent = base.parent if base.parent != Path("") else Path(".")
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
                extra={"backup_dir": self.db._mask_path(str(backup_directory)), "error": str(exc)},
            )
            return

        for obsolete in candidates[retention:]:
            try:
                obsolete.unlink()
            except OSError as exc:
                logger.warning(
                    "db_backup_remove_failed",
                    extra={"backup_path": self.db._mask_path(str(obsolete)), "error": str(exc)},
                )

    # ---- Compatibility helpers expected by tests (typed stubs) ----
    async def _safe_reply(self, message: Any, text: str, *, parse_mode: str | None = None) -> None:
        """Safely reply to a message (legacy-compatible helper)."""
        try:
            if hasattr(message, "reply_text"):
                if parse_mode is not None:
                    await message.reply_text(text, parse_mode=parse_mode)
                else:
                    await message.reply_text(text)
        except Exception:  # noqa: BLE001
            # Swallow in tests; production response path logs and continues.
            pass

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
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            filename = f"{base}-{ts}.json"

            if hasattr(message, "reply_document"):
                bio = io.BytesIO(pretty.encode("utf-8"))
                bio.name = filename
                await message.reply_document(bio, caption="📊 Full Summary JSON attached")
                return

            # Fallback to text
            if hasattr(message, "reply_text"):
                await message.reply_text(f"```json\n{pretty}\n```")
        except Exception:  # noqa: BLE001
            try:
                text = json.dumps(payload, ensure_ascii=False)
                if hasattr(message, "reply_text"):
                    await message.reply_text(text)
            except Exception:
                pass
        _ = metadata

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Adapter used by command/url handlers to process URL flows."""
        await self._handle_url_flow(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
        )

    async def _handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Process a URL message via the URL processor pipeline."""
        await self.url_processor.handle_url_flow(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
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

    def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist a Telegram message snapshot for legacy tests."""
        self.url_processor.message_persistence.persist_message_snapshot(request_id, message)

    async def _on_message(self, message: Any) -> None:
        """Entry point used by tests; delegate to message handler."""
        uid = getattr(getattr(message, "from_user", None), "id", None)
        logger.info("handling_message uid=%s", uid, extra={"uid": uid})
        await self.message_handler.handle_message(message)

    def __setattr__(self, name: str, value: Any) -> None:  # noqa: D401
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
