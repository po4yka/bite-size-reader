import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.llm import LLMClientFactory, LLMClientProtocol
from app.api.background_processor import BackgroundProcessor
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.db.session import DatabaseSessionManager
from app.infrastructure.redis import get_redis

logger = get_logger(__name__)


async def build_background_processor(
    cfg: AppConfig | None = None,
    *,
    db: DatabaseSessionManager | None = None,
    firecrawl: FirecrawlClient | None = None,
    llm_client: LLMClientProtocol | None = None,
    response_formatter: ResponseFormatter | None = None,
    redis_client: Any | None = None,
    semaphore: asyncio.Semaphore | None = None,
    audit_func: Callable[[str, str, dict], None] | None = None,
) -> BackgroundProcessor:
    """Construct a BackgroundProcessor with modern DI-friendly wiring.

    Args:
        cfg: Application configuration. If None, loads from environment.
        db: Database session manager. If None, creates from config.
        firecrawl: Firecrawl client. If None, creates from config.
        llm_client: LLM client (OpenRouter, OpenAI, or Anthropic). If None, creates
                   using LLMClientFactory based on LLM_PROVIDER config.
        response_formatter: Response formatter. If None, creates from config.
        redis_client: Redis client. If None, creates from config.
        semaphore: Concurrency semaphore. If None, creates from config.
        audit_func: Audit callback function. If None, uses default logger.

    Returns:
        Configured BackgroundProcessor instance.
    """

    cfg = cfg or load_config()

    if db is None:
        db = DatabaseSessionManager(
            path=cfg.runtime.db_path,
            operation_timeout=cfg.database.operation_timeout,
            max_retries=cfg.database.max_retries,
            json_max_size=cfg.database.json_max_size,
            json_max_depth=cfg.database.json_max_depth,
            json_max_array_length=cfg.database.json_max_array_length,
            json_max_dict_keys=cfg.database.json_max_dict_keys,
        )

    if firecrawl is None:
        firecrawl = FirecrawlClient(
            api_key=cfg.firecrawl.api_key,
            timeout_sec=cfg.runtime.request_timeout_sec,
            max_retries=cfg.firecrawl.retry_max_attempts,
            backoff_base=cfg.firecrawl.retry_initial_delay,
            debug_payloads=cfg.runtime.debug_payloads,
            max_connections=cfg.firecrawl.max_connections,
            max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
            keepalive_expiry=cfg.firecrawl.keepalive_expiry,
            credit_warning_threshold=cfg.firecrawl.credit_warning_threshold,
            credit_critical_threshold=cfg.firecrawl.credit_critical_threshold,
            max_response_size_mb=cfg.firecrawl.max_response_size_mb,
            max_age_seconds=cfg.firecrawl.max_age_seconds,
            remove_base64_images=cfg.firecrawl.remove_base64_images,
            block_ads=cfg.firecrawl.block_ads,
            skip_tls_verification=cfg.firecrawl.skip_tls_verification,
            include_markdown_format=cfg.firecrawl.include_markdown_format,
            include_html_format=cfg.firecrawl.include_html_format,
            include_links_format=cfg.firecrawl.include_links_format,
            include_summary_format=cfg.firecrawl.include_summary_format,
            include_images_format=cfg.firecrawl.include_images_format,
            enable_screenshot_format=cfg.firecrawl.enable_screenshot_format,
            screenshot_full_page=cfg.firecrawl.screenshot_full_page,
            screenshot_quality=cfg.firecrawl.screenshot_quality,
            screenshot_viewport_width=cfg.firecrawl.screenshot_viewport_width,
            screenshot_viewport_height=cfg.firecrawl.screenshot_viewport_height,
            json_prompt=cfg.firecrawl.json_prompt,
            json_schema=cfg.firecrawl.json_schema,
        )

    if llm_client is None:
        llm_client = LLMClientFactory.create_from_config(cfg, audit=audit_func)

    if response_formatter is None:
        response_formatter = ResponseFormatter(telegram_limits=cfg.telegram_limits)

    if semaphore is None:
        limit = max(1, min(100, cfg.runtime.max_concurrent_calls))
        semaphore = asyncio.Semaphore(limit)

    if redis_client is None:
        redis_client = await get_redis(cfg)

    if audit_func is None:
        audit_func = _default_audit

    url_processor = URLProcessor(
        cfg=cfg,
        db=db,
        firecrawl=firecrawl,
        openrouter=llm_client,  # URLProcessor still uses 'openrouter' param name for compatibility
        response_formatter=response_formatter,
        audit_func=audit_func,
        sem=lambda: semaphore,
    )

    return BackgroundProcessor(
        cfg=cfg,
        db=db,
        url_processor=url_processor,
        redis=redis_client,
        semaphore=semaphore,
        audit_func=audit_func,
    )


def _default_audit(level: str, event: str, details: dict) -> None:
    log_level = logging.INFO if level == "info" else logging.ERROR
    logger.log(log_level, event, extra=details)
