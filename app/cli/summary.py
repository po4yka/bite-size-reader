"""CLI tooling to exercise the /summary command flow locally."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.adapters.content.url_processor import URLProcessor
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.external.response_formatter import ResponseFormatter
from app.adapters.llm import LLMClientFactory
from app.adapters.telegram.command_processor import CommandProcessor
from app.config import AppConfig, load_config
from app.core.logging_utils import generate_correlation_id, setup_json_logging
from app.core.url_utils import extract_all_urls
from app.db.session import DatabaseSessionManager
from app.infrastructure.persistence.sqlite.repositories.audit_log_repository import (
    SqliteAuditLogRepositoryAdapter,
)
from app.services.topic_search import TopicSearchService

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

__all__ = ["main", "run_summary_cli"]


@dataclass(slots=True)
class CLIChat:
    """Lightweight stand-in for Telegram chat metadata."""

    id: int = 0
    type: str = "cli"
    title: str | None = "CLI session"


@dataclass(slots=True)
class CLIUser:
    """Lightweight stand-in for Telegram user metadata."""

    id: int = 0
    is_bot: bool = False
    username: str = "cli-user"


class CLIMessage:
    """Message adapter that mimics the Pyrogram interface for CLI usage."""

    def __init__(self, text: str, *, json_output_path: Path | None = None) -> None:
        self.text = text
        self.caption: str | None = None
        self.id = 0
        self.message_id = 0
        self.chat = CLIChat()
        self.from_user = CLIUser()
        self.entities: list[Any] = []
        self.caption_entities: list[Any] = []
        self.date = None
        self.forward_date = None
        self.forward_from_chat = None
        self.forward_from_message_id = None
        self._json_output_path = json_output_path
        self._last_json: dict[str, Any] | None = None

    async def reply_text(self, text: str, *, parse_mode: str | None = None) -> None:
        """Print reply text to stdout."""
        if parse_mode:
            pass
        else:
            pass
        sys.stdout.flush()

    async def reply_document(self, file_obj: Any, caption: str | None = None) -> None:
        """Print JSON attachment content or persist to file when requested."""
        with contextlib.suppress(Exception):
            file_obj.seek(0)
        data = file_obj.read()
        content = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)

        try:
            self._last_json = json.loads(content)
        except json.JSONDecodeError:
            self._last_json = None

        if self._json_output_path:
            self._json_output_path.parent.mkdir(parents=True, exist_ok=True)
            self._json_output_path.write_text(content, encoding="utf-8")
        else:
            pass

        if caption:
            pass
        sys.stdout.flush()

    def to_dict(self) -> dict[str, Any]:
        """Return a minimal dict representation for persistence helpers."""
        return {
            "text": self.text,
            "chat": {
                "id": self.chat.id,
                "type": self.chat.type,
                "title": self.chat.title,
            },
            "from_user": {
                "id": self.from_user.id,
                "is_bot": self.from_user.is_bot,
                "username": self.from_user.username,
            },
        }


class _SemaphoreFactory:
    """Lazy semaphore factory mirroring the Telegram bot pattern."""

    def __init__(self, permits: int) -> None:
        self._permits = max(1, permits)
        self._sem: asyncio.Semaphore | None = None

    def __call__(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._permits)
        return self._sem


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run the /summary command flow locally for testing",
        allow_abbrev=False,
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Full message text (e.g. '/summary https://example.com/article')",
    )
    parser.add_argument(
        "--url",
        help="Convenience shortcut; builds the message as '/summary <url>'.",
    )
    parser.add_argument(
        "--accept-multiple",
        action="store_true",
        help="Automatically process all URLs when multiple links are supplied.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Override the configured SQLite path for this run.",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        help="Write the final summary JSON to a file instead of stdout.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override the configured log level for this session.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Path to a .env file containing environment variables for the run.",
    )
    return parser.parse_args(argv)


def _resolve_text(args: argparse.Namespace) -> str:
    """Resolve the message text from positional and optional arguments."""
    if args.text and args.url:
        msg = "Specify either a positional message text or --url, not both."
        raise SystemExit(msg)

    if args.url:
        return f"/summary {args.url.strip()}"

    if args.text:
        return args.text

    msg = "Provide a message text or use --url to supply a link to summarize."
    raise SystemExit(msg)


def _load_env_file(path: Path) -> None:
    """Load environment variables from a .env-style file if present."""
    if not path.exists() or not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _prepare_config(args: argparse.Namespace) -> AppConfig:
    """Load configuration, optionally applying CLI overrides."""
    base_dir = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []
    if args.env_file:
        candidates.append(args.env_file)
    else:
        candidates.extend([Path.cwd() / ".env", base_dir / ".env"])

    for candidate in candidates:
        try:
            _load_env_file(candidate)
            if candidate.exists():
                logger.debug("loaded_env_file", extra={"path": str(candidate)})
        except Exception as exc:
            logger.warning("env_file_error", extra={"path": str(candidate), "error": str(exc)})

    try:
        cfg = load_config(allow_stub_telegram=True)
    except RuntimeError as exc:
        msg = (
            "Configuration error: "
            f"{exc}. Set FIRECRAWL_API_KEY and OPENROUTER_API_KEY before running the CLI."
        )
        raise SystemExit(msg) from exc
    runtime = cfg.runtime
    updated = False

    if args.db_path:
        runtime = replace(runtime, db_path=str(args.db_path))
        updated = True

    if args.log_level:
        runtime = replace(runtime, log_level=args.log_level)
        updated = True

    if updated:
        cfg = replace(cfg, runtime=runtime)

    return cfg


_audit_tasks: set[asyncio.Task] = set()


def _build_audit(db: DatabaseSessionManager) -> Callable[[str, str, dict[str, Any]], None]:
    """Create an audit callback compatible with bot components."""
    repo = SqliteAuditLogRepositoryAdapter(db)

    def audit(level: str, event: str, details: dict[str, Any]) -> None:
        try:
            payload: dict[str, Any]
            payload = details if isinstance(details, dict) else {"details": str(details)}
            # Using fire-and-forget task for CLI audit
            task = asyncio.create_task(
                repo.async_insert_audit_log(log_level=level, event_type=event, details=payload)
            )
            _audit_tasks.add(task)
            task.add_done_callback(_audit_tasks.discard)
        except Exception as exc:
            logger.debug(
                "audit_log_failed",
                extra={
                    "event": event,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )

    return audit


async def run_summary_cli(args: argparse.Namespace) -> None:
    """Execute the /summary flow based on parsed CLI arguments."""
    text = _resolve_text(args)
    cfg = _prepare_config(args)

    setup_json_logging(cfg.runtime.log_level)

    db = DatabaseSessionManager(
        path=cfg.runtime.db_path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )
    db.migrate()

    audit = _build_audit(db)
    max_concurrency = cfg.runtime.max_concurrent_calls
    sem_factory = _SemaphoreFactory(max_concurrency)

    response_formatter = ResponseFormatter(telegram_limits=cfg.telegram_limits)

    firecrawl = FirecrawlClient(
        api_key=cfg.firecrawl.api_key,
        timeout_sec=cfg.runtime.request_timeout_sec,
        audit=audit,
        debug_payloads=cfg.runtime.debug_payloads,
        log_truncate_length=cfg.runtime.log_truncate_length,
        max_connections=cfg.firecrawl.max_connections,
        max_keepalive_connections=cfg.firecrawl.max_keepalive_connections,
        keepalive_expiry=cfg.firecrawl.keepalive_expiry,
        credit_warning_threshold=cfg.firecrawl.credit_warning_threshold,
        credit_critical_threshold=cfg.firecrawl.credit_critical_threshold,
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

    # Create LLM client using factory based on LLM_PROVIDER config
    llm_client = LLMClientFactory.create_from_config(cfg, audit=audit)

    # Create topic search service for web search enrichment if enabled
    topic_search = None
    if cfg.web_search.enabled:
        topic_search = TopicSearchService(
            firecrawl=firecrawl,
            max_results=5,
            audit_func=audit,
        )
        logger.info("web_search_enabled_in_cli", extra={"max_queries": cfg.web_search.max_queries})

    url_processor = URLProcessor(
        cfg=cfg,
        db=db,
        firecrawl=firecrawl,
        openrouter=llm_client,  # URLProcessor still uses 'openrouter' param name for compatibility
        response_formatter=response_formatter,
        audit_func=audit,
        sem=sem_factory,
        topic_search=topic_search,
    )

    command_processor = CommandProcessor(
        cfg=cfg,
        response_formatter=response_formatter,
        db=db,
        url_processor=url_processor,
        audit_func=audit,
    )

    message = CLIMessage(text=text, json_output_path=args.json_path)

    correlation_id = generate_correlation_id()
    logger.info("cli_summary_start", extra={"cid": correlation_id})

    try:
        next_action, _ = await command_processor.handle_summarize_command(
            message=message,
            text=text,
            uid=message.from_user.id,
            correlation_id=correlation_id,
            interaction_id=0,
            start_time=time.time(),
        )

        if next_action == "multi_confirm" and args.accept_multiple:
            urls = extract_all_urls(text)
            await response_formatter.safe_reply(
                message, f"Auto-confirmed processing of {len(urls)} link(s)."
            )
            for url in urls:
                per_cid = generate_correlation_id()
                logger.info(
                    "cli_summary_link",
                    extra={"cid": per_cid, "url": url},
                )
                await url_processor.handle_url_flow(message, url, correlation_id=per_cid)
        elif next_action == "multi_confirm":
            pass

    finally:
        await firecrawl.aclose()
        await llm_client.aclose()


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m app.cli.summary``."""
    args = parse_args(argv)
    try:
        asyncio.run(run_summary_cli(args))
    except KeyboardInterrupt:  # pragma: no cover - user cancelled
        return 1
    except Exception as exc:
        logger.exception("cli_summary_failed", exc_info=exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
