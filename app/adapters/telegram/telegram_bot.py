# ruff: noqa: E501
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass

from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.telegram.forward_processor import ForwardProcessor
from app.adapters.telegram.message_handler import MessageHandler
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.telegram.telegram_client import TelegramClient
from app.adapters.content.url_processor import URLProcessor
from app.config import AppConfig
from app.core.logging_utils import setup_json_logging
from app.db.database import Database

logger = logging.getLogger(__name__)


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
            extra={"db_path": self.cfg.runtime.db_path, "log_level": self.cfg.runtime.log_level},
        )

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
        self.response_formatter = ResponseFormatter()

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

        self.telegram_client = TelegramClient(cfg=self.cfg)

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
        await self.telegram_client.start(self.message_handler.handle_message)

    def _audit(self, level: str, event: str, details: dict) -> None:
        """Audit log helper."""
        try:
            self.db.insert_audit_log(
                level=level, event=event, details_json=json.dumps(details, ensure_ascii=False)
            )
        except Exception as e:  # noqa: BLE001
            logger.error("audit_persist_failed", extra={"error": str(e), "event": event})
