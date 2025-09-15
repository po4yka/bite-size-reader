# ruff: noqa: E501
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.adapters.firecrawl_parser import FirecrawlClient
from app.adapters.openrouter_client import OpenRouterClient
from app.config import AppConfig
from app.core.html_utils import (
    chunk_sentences,
    clean_markdown_article_text,
    html_to_text,
    normalize_with_textacy,
    split_sentences,
)
from app.core.lang import LANG_RU, choose_language, detect_language
from app.core.logging_utils import generate_correlation_id, setup_json_logging
from app.core.summary_contract import validate_and_shape_summary
from app.core.telegram_models import TelegramMessage
from app.core.url_utils import extract_all_urls, looks_like_url, normalize_url, url_hash_sha256
from app.db.database import Database

try:
    from pyrogram import Client, filters
    from pyrogram.types import Message
except Exception:  # pragma: no cover - allow import in environments without deps
    Client = object
    filters = None
    Message = object


logger = logging.getLogger(__name__)


@dataclass
class TelegramBot:
    cfg: AppConfig
    db: Database

    def __post_init__(self) -> None:
        setup_json_logging(self.cfg.runtime.log_level)
        logger.info(
            "bot_init",
            extra={"db_path": self.cfg.runtime.db_path, "log_level": self.cfg.runtime.log_level},
        )

        # Init clients
        self._firecrawl = FirecrawlClient(
            api_key=self.cfg.firecrawl.api_key,
            timeout_sec=self.cfg.runtime.request_timeout_sec,
            audit=self._audit,
            debug_payloads=self.cfg.runtime.debug_payloads,
            log_truncate_length=self.cfg.runtime.log_truncate_length,
        )
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
        )

        # Telegram client (PyroTGFork/Pyrogram)
        if Client is object:
            self.client = None
        else:
            self.client = Client(
                name="bite_size_reader_bot",
                api_id=self.cfg.telegram.api_id,
                api_hash=self.cfg.telegram.api_hash,
                bot_token=self.cfg.telegram.bot_token,
                in_memory=True,
            )
        # simple in-memory state: users awaiting a URL after /summarize
        self._awaiting_url_users: set[int] = set()
        # pending multiple links confirmation: uid -> list of urls
        self._pending_multi_links: dict[int, list[str]] = {}
        # Limit concurrent outbound calls (Firecrawl / OpenRouter)
        max_conc = int(os.getenv("MAX_CONCURRENT_CALLS", "4"))
        self._ext_sem = asyncio.Semaphore(max(1, max_conc))

    async def start(self) -> None:
        if not self.client:
            logger.warning("telegram_client_not_available")
            return

        # Register handlers only if filters are available
        if filters:
            # Register a simple on_message handler in private chats
            client_any: Any = self.client

            @client_any.on_message(filters.private)
            async def _handler(client: Any, message: Any) -> None:  # noqa: ANN401
                await self._on_message(message)

        await client_any.start()
        logger.info("bot_started")
        await self._setup_bot_commands()
        await idle()

    async def _on_message(self, message: Any) -> None:
        start_time = time.time()
        interaction_id = 0
        try:
            correlation_id = generate_correlation_id()

            # Parse message using comprehensive model for better validation
            telegram_message = TelegramMessage.from_pyrogram_message(message)

            # Validate message and log any issues
            validation_errors = telegram_message.validate()
            if validation_errors:
                logger.warning(
                    "message_validation_errors",
                    extra={
                        "cid": correlation_id,
                        "errors": validation_errors,
                        "message_id": telegram_message.message_id,
                    },
                )

            # Extract message details for logging using validated model
            uid = telegram_message.from_user.id if telegram_message.from_user else 0
            # Ensure uid is an integer for consistent comparison
            try:
                uid = int(uid)
            except (ValueError, TypeError):
                uid = 0
                logger.warning(f"Invalid user ID type: {type(uid)}, setting to 0")

            logger.info(f"Checking access for UID: {uid} (type: {type(uid)})")
            logger.info(
                f"Allowed user IDs: {self.cfg.telegram.allowed_user_ids} (type: {type(self.cfg.telegram.allowed_user_ids)})"
            )
            chat_id = telegram_message.chat.id if telegram_message.chat else None
            message_id = telegram_message.message_id
            text = telegram_message.get_effective_text() or ""

            # Check for forwarded message using validated model
            has_forward = telegram_message.is_forwarded
            forward_from_chat_id = None
            forward_from_chat_title = None
            forward_from_message_id = None

            if has_forward:
                if telegram_message.forward_from_chat:
                    forward_from_chat_id = telegram_message.forward_from_chat.id
                    forward_from_chat_title = telegram_message.forward_from_chat.title
                forward_from_message_id = telegram_message.forward_from_message_id

            # Get media type using validated model
            media_type = telegram_message.media_type.value if telegram_message.media_type else None

            # Extract entities for logging using validated model
            entities_json = None
            entities = telegram_message.get_effective_entities()
            if entities:
                try:
                    entities_json = json.dumps(
                        [entity.__dict__ for entity in entities], ensure_ascii=False
                    )
                except Exception:
                    entities_json = None

            # Determine interaction type using validated model
            interaction_type = "unknown"
            command = None
            input_url = None

            if telegram_message.is_command():
                interaction_type = "command"
                command = telegram_message.get_command()
            elif has_forward:
                interaction_type = "forward"
            elif text and looks_like_url(text):
                interaction_type = "url"
                urls = extract_all_urls(text)
                input_url = urls[0] if urls else None
            elif text:
                interaction_type = "text"

            # Log the initial user interaction
            interaction_id = self._log_user_interaction(
                user_id=uid,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=text[:1000] if text else None,  # Limit text length
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                entities_json=entities_json,
                correlation_id=correlation_id,
            )

            # Owner-only gate - improved validation with better debugging
            if self.cfg.telegram.allowed_user_ids:
                logger.info(
                    f"Access control enabled. Checking if UID {uid} is in allowed list: {self.cfg.telegram.allowed_user_ids}"
                )
                if uid not in self.cfg.telegram.allowed_user_ids:
                    logger.warning(
                        f"Access denied for UID {uid}. Not in allowed list: {self.cfg.telegram.allowed_user_ids}"
                    )
                else:
                    logger.info(f"Access granted for UID {uid}. Found in allowed list.")
            else:
                logger.info("Access control disabled - no allowed_user_ids configured")

            if self.cfg.telegram.allowed_user_ids and uid not in self.cfg.telegram.allowed_user_ids:
                await self._safe_reply(
                    message,
                    f"This bot is private. Access denied. Error ID: {correlation_id}",
                )
                logger.info("access_denied", extra={"uid": uid, "cid": correlation_id})
                try:
                    self._audit("WARN", "access_denied", {"uid": uid, "cid": correlation_id})
                except Exception:
                    pass

                # Update interaction with access denied
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="error",
                        error_occurred=True,
                        error_message="Access denied",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                return

            # Commands
            if text.startswith("/start"):
                logger.info(
                    "command_start",
                    extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
                )
                try:
                    self._audit(
                        "INFO",
                        "command_start",
                        {"uid": uid, "chat_id": chat_id, "cid": correlation_id},
                    )
                except Exception:
                    pass
                await self._send_welcome(message)
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="welcome",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                return
            if text.startswith("/help"):
                logger.info(
                    "command_help",
                    extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
                )
                try:
                    self._audit(
                        "INFO",
                        "command_help",
                        {"uid": uid, "chat_id": chat_id, "cid": correlation_id},
                    )
                except Exception:
                    pass
                await self._send_help(message)
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="help",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                return
            if text.startswith("/summarize_all"):
                urls = extract_all_urls(text)
                if len(urls) == 0:
                    await self._safe_reply(
                        message,
                        "Send multiple URLs in one message after /summarize_all, separated by space or new line.",
                    )
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="error",
                            error_occurred=True,
                            error_message="No URLs found",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                    return
                logger.info(
                    "command_summarize_all",
                    extra={
                        "uid": uid,
                        "chat_id": chat_id,
                        "cid": correlation_id,
                        "count": len(urls),
                    },
                )
                try:
                    self._audit(
                        "INFO",
                        "command_summarize_all",
                        {"uid": uid, "chat_id": chat_id, "cid": correlation_id, "count": len(urls)},
                    )
                except Exception:
                    pass
                await self._safe_reply(message, f"Processing {len(urls)} links...")
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="processing",
                        processing_time_ms=int((time.time() - start_time) * 1000),
                    )
                for u in urls:
                    per_link_cid = generate_correlation_id()
                    logger.debug(
                        "processing_link", extra={"uid": uid, "url": u, "cid": per_link_cid}
                    )
                    await self._handle_url_flow(message, u, correlation_id=per_link_cid)
                return

            if text.startswith("/summarize"):
                # If URL is in the same message, extract and process; otherwise set awaiting state
                urls = extract_all_urls(text)
                logger.info(
                    "command_summarize",
                    extra={
                        "uid": uid,
                        "chat_id": chat_id,
                        "cid": correlation_id,
                        "with_urls": bool(urls),
                        "count": len(urls),
                    },
                )
                try:
                    self._audit(
                        "INFO",
                        "command_summarize",
                        {
                            "uid": uid,
                            "chat_id": chat_id,
                            "cid": correlation_id,
                            "with_urls": bool(urls),
                            "count": len(urls),
                        },
                    )
                except Exception:
                    pass
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="confirmation",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                elif len(urls) == 1:
                    await self._handle_url_flow(
                        message,
                        urls[0],
                        correlation_id=correlation_id,
                        interaction_id=interaction_id,
                    )
                else:
                    self._awaiting_url_users.add(uid)
                    await self._safe_reply(message, "Send a URL to summarize.")
                    logger.debug("awaiting_url", extra={"uid": uid})
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="awaiting_url",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                return

            # If awaiting a URL due to prior /summarize
            if uid in self._awaiting_url_users and looks_like_url(text):
                urls = extract_all_urls(text)
                self._awaiting_url_users.discard(uid)
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="confirmation",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                    return
                if len(urls) == 1:
                    logger.debug("received_awaited_url", extra={"uid": uid})
                    await self._handle_url_flow(
                        message,
                        urls[0],
                        correlation_id=correlation_id,
                        interaction_id=interaction_id,
                    )
                    return

            if text and looks_like_url(text):
                urls = extract_all_urls(text)
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="confirmation",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                elif len(urls) == 1:
                    await self._handle_url_flow(
                        message,
                        urls[0],
                        correlation_id=correlation_id,
                        interaction_id=interaction_id,
                    )
                return

            # Handle yes/no responses for pending multi-link confirmation
            if uid in self._pending_multi_links:
                if self._is_affirmative(text):
                    urls = self._pending_multi_links.pop(uid)
                    await self._safe_reply(message, f"Processing {len(urls)} links...")
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="processing",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                    for u in urls:
                        per_link_cid = generate_correlation_id()
                        logger.debug(
                            "processing_link",
                            extra={"uid": uid, "url": u, "cid": per_link_cid},
                        )
                        await self._handle_url_flow(message, u, correlation_id=per_link_cid)
                    return
                if self._is_negative(text):
                    self._pending_multi_links.pop(uid, None)
                    await self._safe_reply(message, "Cancelled.")
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="cancelled",
                            processing_time_ms=int((time.time() - start_time) * 1000),
                        )
                    return

            if getattr(message, "forward_from_chat", None) and getattr(
                message, "forward_from_message_id", None
            ):
                await self._handle_forward_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return

            await self._safe_reply(message, "Send a URL or forward a channel post.")
            logger.debug(
                "unknown_input",
                extra={
                    "has_forward": bool(getattr(message, "forward_from_chat", None)),
                    "text_len": len(text),
                },
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="unknown_input",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("handler_error", extra={"cid": correlation_id})
            try:
                self._audit("ERROR", "unhandled_error", {"cid": correlation_id, "error": str(e)})
            except Exception:
                pass
            await self._safe_reply(
                message,
                f"An unexpected error occurred. Error ID: {correlation_id}. Please try again.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(e)[:500],  # Limit error message length
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

    async def _send_help(self, message: Any) -> None:
        help_text = (
            "Bite-Size Reader\n\n"
            "Commands:\n"
            "- /help — show this help.\n"
            "- /summarize <URL> — summarize a URL.\n"
            "- /summarize_all <URLs> — summarize multiple URLs from one message.\n\n"
            "Usage:\n"
            "- You can simply send a URL (or several URLs) or forward a channel post — commands are optional.\n"
            "- You can also send /summarize and then a URL in the next message.\n"
            "- Multiple links in one message are supported; I can confirm or use /summarize_all to process immediately."
        )
        await self._safe_reply(message, help_text)

    async def _send_welcome(self, message: Any) -> None:
        welcome = (
            "Welcome to Bite-Size Reader!\n\n"
            "What I do:\n"
            "- Summarize articles from URLs using Firecrawl + OpenRouter.\n"
            "- Summarize forwarded channel posts.\n\n"
            "How to use:\n"
            "- Send a URL directly, or use /summarize <URL>.\n"
            "- You can also send /summarize and then the URL in the next message.\n"
            "- For forwarded posts, use /summarize_forward and then forward a channel post.\n"
            '- Multiple links in one message are supported: I will ask "Process N links?" or use /summarize_all to process immediately.\n\n'
            "Notes:\n"
            "- I reply with a strict JSON object.\n"
            "- Errors include an Error ID you can reference in logs."
        )
        await self._safe_reply(message, welcome)

    async def _setup_bot_commands(self) -> None:
        if not self.client or Client is object:
            return
        try:
            from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats

            commands_en = [
                BotCommand("start", "Welcome and instructions"),
                BotCommand("help", "Show help and usage"),
                BotCommand("summarize", "Summarize a URL (send URL next)"),
                BotCommand("summarize_all", "Summarize multiple URLs from one message"),
                BotCommand("summarize_forward", "Summarize the next forwarded channel post"),
            ]
            commands_ru = [
                BotCommand("start", "Приветствие и инструкция"),
                BotCommand("help", "Показать помощь и инструкцию"),
                BotCommand("summarize", "Суммировать ссылку (или пришлите позже)"),
                BotCommand("summarize_all", "Суммировать несколько ссылок из сообщения"),
                BotCommand("summarize_forward", "Суммировать следующий пересланный пост"),
            ]
            try:
                client_any: Any = self.client
                # Default and private scope
                await client_any.set_bot_commands(commands_en)
                await client_any.set_bot_commands(
                    commands_en, scope=BotCommandScopeAllPrivateChats()
                )
                # Localized RU
                await client_any.set_bot_commands(commands_ru, language_code="ru")
                await client_any.set_bot_commands(
                    commands_ru,
                    scope=BotCommandScopeAllPrivateChats(),
                    language_code="ru",
                )
                # Optional descriptions (if supported)
                try:
                    await client_any.set_bot_description(
                        "Summarize URLs and forwarded posts into a strict JSON.",
                        language_code="en",
                    )
                    await client_any.set_bot_short_description(
                        "Summarize links & posts (JSON)", language_code="en"
                    )
                    await client_any.set_bot_description(
                        "Краткие резюме ссылок и пересланных постов в формате JSON.",
                        language_code="ru",
                    )
                    await client_any.set_bot_short_description(
                        "Резюме ссылок и постов (JSON)", language_code="ru"
                    )
                except Exception:
                    pass
                # Ensure default menu button (best-effort)
                try:
                    await client_any.set_chat_menu_button()
                except Exception:
                    pass
                logger.info(
                    "bot_commands_set",
                    extra={"count_en": len(commands_en), "count_ru": len(commands_ru)},
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("bot_commands_set_failed", extra={"error": str(e)})
        except Exception:
            return

    async def _handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        norm = normalize_url(url_text)
        dedupe = url_hash_sha256(norm)
        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm, "hash": dedupe, "cid": correlation_id},
        )
        # Notify: request accepted
        try:
            await self._safe_reply(message, "Accepted. Fetching content...")
        except Exception:
            pass
        # Dedupe check
        existing_req = self.db.get_request_by_dedupe_hash(dedupe)
        req_id: int  # Initialize variable for type checker
        if existing_req:
            req_id = int(existing_req["id"])  # reuse existing request
            self._audit(
                "INFO",
                "url_dedupe_hit",
                {"request_id": req_id, "hash": dedupe, "url": url_text, "cid": correlation_id},
            )
            if correlation_id:
                try:
                    self.db.update_request_correlation_id(req_id, correlation_id)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "persist_cid_error", extra={"error": str(e), "cid": correlation_id}
                    )
        else:
            # Create request row (pending)
            chat_obj = getattr(message, "chat", None)
            chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
            chat_id = int(chat_id_raw) if chat_id_raw is not None else None

            from_user_obj = getattr(message, "from_user", None)
            user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
            user_id = int(user_id_raw) if user_id_raw is not None else None

            msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
            input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

            req_id = self.db.create_request(
                type_="url",
                status="pending",
                correlation_id=correlation_id,
                chat_id=chat_id,
                user_id=user_id,
                input_url=url_text,
                normalized_url=norm,
                dedupe_hash=dedupe,
                input_message_id=input_message_id,
                route_version=URL_ROUTE_VERSION,
            )

            # Snapshot telegram message (only on first request for this URL)
            try:
                self._persist_message_snapshot(req_id, message)
            except Exception as e:  # noqa: BLE001
                logger.error("snapshot_error", extra={"error": str(e), "cid": correlation_id})

        # Note: We don't reuse summaries here to allow version increment on dedupe
        # The request is deduped (reused), but summaries are always regenerated

        # Firecrawl or reuse existing crawl result
        existing_crawl = self.db.get_crawl_result_by_request(req_id)
        if existing_crawl and (
            existing_crawl.get("content_markdown") or existing_crawl.get("content_html")
        ):
            md = existing_crawl.get("content_markdown")
            if md:
                content_text = clean_markdown_article_text(md)
            else:
                content_text = html_to_text(existing_crawl.get("content_html") or "")
            # Optional normalization (feature-flagged)
            try:
                if getattr(self.cfg.runtime, "enable_textacy", False):
                    content_text = normalize_with_textacy(content_text)
            except Exception:
                pass
            self._audit("INFO", "reuse_crawl_result", {"request_id": req_id, "cid": correlation_id})
            try:
                await self._safe_reply(
                    message,
                    "Reusing cached fetch result.",
                )
            except Exception:
                pass
        else:
            # Notify: starting Firecrawl
            try:
                await self._safe_reply(message, "Fetching via Firecrawl...")
            except Exception:
                pass
            async with self._ext_sem:
                crawl = await self._firecrawl.scrape_markdown(url_text, request_id=req_id)
            try:
                self.db.insert_crawl_result(
                    request_id=req_id,
                    source_url=crawl.source_url,
                    endpoint=crawl.endpoint,
                    http_status=crawl.http_status,
                    status=crawl.status,
                    options_json=json.dumps(crawl.options_json or {}),
                    content_markdown=crawl.content_markdown,
                    content_html=crawl.content_html,
                    structured_json=json.dumps(crawl.structured_json or {}),
                    metadata_json=json.dumps(crawl.metadata_json or {}),
                    links_json=json.dumps(crawl.links_json or {}),
                    screenshots_paths_json=None,
                    raw_response_json=json.dumps(crawl.raw_response_json or {}),
                    latency_ms=crawl.latency_ms,
                    error_text=crawl.error_text,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("persist_crawl_error", extra={"error": str(e), "cid": correlation_id})

            # Debug logging for crawl result
            logger.debug(
                "crawl_result_debug",
                extra={
                    "cid": correlation_id,
                    "status": crawl.status,
                    "http_status": crawl.http_status,
                    "error_text": crawl.error_text,
                    "has_markdown": bool(crawl.content_markdown),
                    "has_html": bool(crawl.content_html),
                    "markdown_len": len(crawl.content_markdown) if crawl.content_markdown else 0,
                    "html_len": len(crawl.content_html) if crawl.content_html else 0,
                },
            )

            if crawl.status != "ok" or not (crawl.content_markdown or crawl.content_html):
                self.db.update_request_status(req_id, "error")
                await self._safe_reply(
                    message,
                    f"Failed to fetch content. Error ID: {correlation_id}",
                )
                logger.error(
                    "firecrawl_error",
                    extra={
                        "error": crawl.error_text,
                        "cid": correlation_id,
                        "status": crawl.status,
                        "http_status": crawl.http_status,
                    },
                )
                try:
                    self._audit(
                        "ERROR",
                        "firecrawl_error",
                        {"request_id": req_id, "cid": correlation_id, "error": crawl.error_text},
                    )
                except Exception:
                    pass

                # Update interaction with error
                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="error",
                        error_occurred=True,
                        error_message=f"Firecrawl error: {crawl.error_text or 'Unknown error'}",
                        request_id=req_id,
                    )
                return
            # Notify: Firecrawl success
            try:
                excerpt_len = (len(crawl.content_markdown) if crawl.content_markdown else 0) or (
                    len(crawl.content_html) if crawl.content_html else 0
                )
                await self._safe_reply(
                    message,
                    (
                        f"Fetched ✓ (HTTP {crawl.http_status or 'n/a'}, "
                        f"~{excerpt_len} chars, {crawl.latency_ms or 0} ms)."
                    ),
                )
            except Exception:
                pass
            if crawl.content_markdown:
                content_text = clean_markdown_article_text(crawl.content_markdown)
            else:
                content_text = html_to_text(crawl.content_html or "")
            # Optional normalization (feature-flagged)
            try:
                if getattr(self.cfg.runtime, "enable_textacy", False):
                    content_text = normalize_with_textacy(content_text)
            except Exception:
                pass

        # Language detection and choice
        detected = detect_language(content_text or "")
        try:
            self.db.update_request_lang_detected(req_id, detected)
        except Exception as e:  # noqa: BLE001
            logger.error("persist_lang_detected_error", extra={"error": str(e)})
        chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
        system_prompt = await self._load_system_prompt(chosen_lang)
        logger.debug(
            "language_choice",
            extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
        )
        # Notify: language detected
        try:
            await self._safe_reply(
                message,
                f"Language detected: {detected or 'unknown'}. Generating summary...",
            )
        except Exception:
            pass

        # LLM - chunk long content (map -> reduce)
        enable_chunking = getattr(self.cfg.runtime, "enable_chunking", False)
        max_chars = int(getattr(self.cfg.runtime, "chunk_max_chars", 200000))
        content_len = len(content_text)
        text_for_summary = content_text
        chunks: list[str] | None = None
        if enable_chunking and content_len > max_chars:
            logger.info(
                "chunking_enabled",
                extra={"cid": correlation_id, "max_chars": max_chars},
            )
            try:
                sentences = split_sentences(content_text, "ru" if chosen_lang == LANG_RU else "en")
                chunks = chunk_sentences(sentences, max_chars=2000)
            except Exception:
                chunks = None
        # Inform the user how the content will be handled
        try:
            if enable_chunking and content_len > max_chars and (chunks or []):
                await self._safe_reply(
                    message,
                    (
                        f"Content length: ~{content_len:,} chars. "
                        f"Chunking into {len(chunks or [])} parts (≤2000 chars each) + final merge."
                    ),
                )
            elif not enable_chunking and content_len > max_chars:
                await self._safe_reply(
                    message,
                    (
                        f"Content length: ~{content_len:,} chars exceeds {max_chars:,}. "
                        "Chunking is disabled; attempting single-pass summary."
                    ),
                )
            else:
                await self._safe_reply(
                    message,
                    f"Content length: ~{content_len:,} chars. Single-pass summary.",
                )
            logger.info(
                "content_handling",
                extra={
                    "cid": correlation_id,
                    "length": content_len,
                    "enable_chunking": enable_chunking,
                    "threshold": max_chars,
                    "chunks": (
                        len(chunks or []) if enable_chunking and content_len > max_chars else 1
                    ),
                },
            )
        except Exception:
            pass

        if chunks and len(chunks) > 1:
            partials: list[str] = []
            for idx, chunk in enumerate(chunks, start=1):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Analyze this part {idx}/{len(chunks)} and output ONLY a valid JSON object matching the schema. "
                            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n"
                            f"CONTENT START\n{chunk}\nCONTENT END"
                        ),
                    },
                ]
                async with self._ext_sem:
                    resp = await self._openrouter.chat(
                        messages,
                        temperature=self.cfg.openrouter.temperature,
                        max_tokens=self.cfg.openrouter.max_tokens,
                        top_p=self.cfg.openrouter.top_p,
                        request_id=req_id,
                    )
                if resp.status == "ok" and resp.response_text:
                    partials.append(resp.response_text)
            # Merge step: concatenate partials as context for a final merge summary
            merged_context = "\n\n".join(partials) if partials else content_text
            text_for_summary = merged_context

        # Validate content before sending to LLM
        user_content = (
            f"Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. Do NOT include any text outside the JSON.\n\n"
            f"CONTENT START\n{text_for_summary}\nCONTENT END"
        )

        logger.info(
            "llm_content_validation",
            extra={
                "cid": correlation_id,
                "system_prompt_len": len(system_prompt),
                "user_content_len": len(user_content),
                "text_for_summary_len": len(text_for_summary),
                "text_preview": (
                    text_for_summary[:200] + "..."
                    if len(text_for_summary) > 200
                    else text_for_summary
                ),
                "has_content": bool(text_for_summary.strip()),
            },
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        async with self._ext_sem:
            # Provide structured outputs schema through response_format
            response_format: dict[str, object] = {"type": "json_object"}
            try:
                from app.core.summary_contract import get_summary_json_schema

                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "summary_schema",
                        "schema": get_summary_json_schema(),
                        "strict": True,
                    },
                }
            except Exception:
                pass

            llm = await self._openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=(self.cfg.openrouter.max_tokens or 2048),
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=response_format,
            )
        # Notify: LLM finished (success or error will be handled below)
        try:
            status_emoji = "✅" if llm.status == "ok" else "❌"
            model_name = llm.model or self.cfg.openrouter.model
            latency_sec = (llm.latency_ms or 0) / 1000.0

            if llm.status == "ok":
                # Success message with token usage and cost
                tokens_used = (llm.tokens_prompt or 0) + (llm.tokens_completion or 0)
                cost_info = f", ${llm.cost_usd:.4f}" if llm.cost_usd else ""
                await self._safe_reply(
                    message,
                    (
                        f"{status_emoji} LLM call completed successfully\n"
                        f"Model: {model_name}\n"
                        f"Latency: {latency_sec:.1f}s\n"
                        f"Tokens: {tokens_used:,}{cost_info}"
                    ),
                )
            else:
                # Error message with detailed error information
                error_details = []
                if llm.error_text:
                    error_details.append(f"Error: {llm.error_text}")
                if hasattr(llm, "response_json") and llm.response_json:
                    error_data = llm.response_json.get("error", {})
                    if error_data:
                        if error_data.get("code"):
                            error_details.append(f"Code: {error_data['code']}")
                        if error_data.get("type"):
                            error_details.append(f"Type: {error_data['type']}")
                        if error_data.get("param"):
                            error_details.append(f"Parameter: {error_data['param']}")
                        if error_data.get("metadata"):
                            metadata = error_data["metadata"]
                            if metadata.get("provider_name"):
                                error_details.append(f"Provider: {metadata['provider_name']}")
                            if metadata.get("raw"):
                                # Parse raw error for more details
                                try:
                                    raw_error = json.loads(metadata["raw"])
                                    if raw_error.get("error", {}).get("message"):
                                        error_details.append(
                                            f"Provider error: {raw_error['error']['message']}"
                                        )
                                except Exception:
                                    pass

                error_text = "\n".join(error_details) if error_details else "Unknown error"
                await self._safe_reply(
                    message,
                    (
                        f"{status_emoji} LLM call failed\n"
                        f"Model: {model_name}\n"
                        f"Latency: {latency_sec:.1f}s\n"
                        f"{error_text}\n"
                        f"Error ID: {correlation_id}"
                    ),
                )
        except Exception:
            pass

        # Async optimization: Run database operations concurrently with response processing
        async def _persist_llm_call():
            try:
                self.db.insert_llm_call(
                    request_id=req_id,
                    provider="openrouter",
                    model=llm.model or self.cfg.openrouter.model,
                    endpoint=llm.endpoint,
                    request_headers_json=json.dumps(llm.request_headers or {}),
                    request_messages_json=json.dumps(llm.request_messages or []),
                    response_text=llm.response_text,
                    response_json=json.dumps(llm.response_json or {}),
                    tokens_prompt=llm.tokens_prompt,
                    tokens_completion=llm.tokens_completion,
                    cost_usd=llm.cost_usd,
                    latency_ms=llm.latency_ms,
                    status=llm.status,
                    error_text=llm.error_text,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})

        # Start database persistence in background
        import asyncio

        asyncio.create_task(_persist_llm_call())  # Fire and forget for performance

        if llm.status != "ok":
            self.db.update_request_status(req_id, "error")
            # Detailed error message already sent above, just log for debugging
            logger.error("openrouter_error", extra={"error": llm.error_text, "cid": correlation_id})
            try:
                self._audit(
                    "ERROR",
                    "openrouter_error",
                    {"request_id": req_id, "cid": correlation_id, "error": llm.error_text},
                )
            except Exception:
                pass

            # Update interaction with error
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=f"LLM error: {llm.error_text or 'Unknown error'}",
                    request_id=req_id,
                )
            return

        # Best-effort parse + validate
        try:
            llm_text = llm.response_text or ""
            raw = llm_text.strip().strip("` ")
            summary_json = json.loads(raw)
        except Exception:
            try:
                logger.error(
                    "json_parse_failed_preview",
                    extra={
                        "cid": correlation_id,
                        "preview": (llm.response_text or "")[
                            : self.cfg.runtime.log_truncate_length
                        ],
                        "tail": (llm.response_text or "")[-self.cfg.runtime.log_truncate_length :],
                    },
                )
            except Exception:
                pass
            llm_text = llm.response_text or ""
            start = llm_text.find("{")
            end = llm_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                try:
                    logger.error(
                        "json_missing_brace",
                        extra={
                            "cid": correlation_id,
                            "head": (llm.response_text or "")[
                                : self.cfg.runtime.log_truncate_length
                            ],
                            "tail": (llm.response_text or "")[
                                -self.cfg.runtime.log_truncate_length :
                            ],
                        },
                    )
                except Exception:
                    pass
                # Attempt one repair using assistant prefill best-practice
                try:
                    logger.info("json_repair_attempt", extra={"cid": correlation_id})
                    llm_text = llm.response_text or ""
                    repair_messages: list[dict[str, str]] = [
                        {"role": "system", "content": system_prompt},
                        {"role": "assistant", "content": llm_text},
                        {
                            "role": "user",
                            "content": (
                                "Your previous message was not a valid JSON object. "
                                "Respond with ONLY a corrected JSON that matches the schema exactly."
                            ),
                        },
                    ]
                    async with self._ext_sem:
                        repair = await self._openrouter.chat(
                            repair_messages,
                            temperature=self.cfg.openrouter.temperature,
                            max_tokens=(self.cfg.openrouter.max_tokens or 2048),
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                        )
                    if repair.status == "ok" and (repair.response_text or "").strip():
                        try:
                            summary_json = json.loads(
                                (repair.response_text or "").strip().strip("` ")
                            )
                        except Exception:
                            try:
                                logger.error(
                                    "json_repair_parse_failed_preview",
                                    extra={
                                        "cid": correlation_id,
                                        "preview": (repair.response_text or "")[
                                            : self.cfg.runtime.log_truncate_length
                                        ],
                                        "tail": (repair.response_text or "")[
                                            -self.cfg.runtime.log_truncate_length :
                                        ],
                                    },
                                )
                            except Exception:
                                pass
                            repair_text = repair.response_text or ""
                            rs = repair_text.find("{")
                            re_ = repair_text.rfind("}")
                            if rs != -1 and re_ != -1 and re_ > rs:
                                summary_json = json.loads(repair_text[rs : re_ + 1])
                            else:
                                raise ValueError("repair_failed")
                    else:
                        raise ValueError("repair_call_error")
                except Exception:
                    self.db.update_request_status(req_id, "error")
                    await self._safe_reply(
                        message, f"Invalid summary format. Error ID: {correlation_id}"
                    )

                    # Update interaction with error
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="error",
                            error_occurred=True,
                            error_message="Invalid summary format",
                            request_id=req_id,
                        )
                    return
            else:
                llm_text = llm.response_text or ""
                summary_json = json.loads(llm_text[start : end + 1])

        shaped = validate_and_shape_summary(summary_json)

        # Enhanced llm_finished log with summary details
        logger.info(
            "llm_finished",
            extra={
                "status": llm.status,
                "latency_ms": llm.latency_ms,
                "model": llm.model,
                "cid": correlation_id,
                "summary_250_len": len(shaped.get("summary_250", "")),
                "summary_1000_len": len(shaped.get("summary_1000", "")),
                "key_ideas_count": len(shaped.get("key_ideas", [])),
                "topic_tags_count": len(shaped.get("topic_tags", [])),
                "entities_count": len(shaped.get("entities", [])),
                "reading_time_min": shaped.get("estimated_reading_time_min"),
                "seo_keywords_count": len(shaped.get("seo_keywords", [])),
            },
        )

        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(shaped)
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        # Update interaction with successful completion
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

        # Send combined preview and JSON in one message to reduce API calls
        try:
            preview_lines = [
                "✅ Summary Complete:",
                "",
                "📋 **TL;DR:**",
                str(shaped.get("summary_250", "")).strip(),
            ]

            tags = shaped.get("topic_tags") or []
            if tags:
                preview_lines.extend(["", "🏷️ **Tags:** " + " ".join(tags[:6])])

            ideas = [str(x).strip() for x in (shaped.get("key_ideas") or []) if str(x).strip()]
            if ideas:
                preview_lines.extend(["", "💡 **Key Ideas:**"])
                for idea in ideas[:3]:
                    preview_lines.append(f"• {idea}")

            preview_lines.extend(["", "📊 **Full JSON:**"])

            # Combine preview and JSON in one message
            combined_message = "\n".join(preview_lines)
            await self._safe_reply(message, combined_message)

            # Send JSON as separate code block for better formatting
            await self._reply_json(message, shaped)

        except Exception:
            # Fallback to separate messages
            try:
                preview_lines = [
                    "TL;DR:",
                    str(shaped.get("summary_250", "")).strip(),
                ]
                tags = shaped.get("topic_tags") or []
                if tags:
                    preview_lines.append("Tags: " + " ".join(tags[:6]))
                ideas = [str(x).strip() for x in (shaped.get("key_ideas") or []) if str(x).strip()]
                for idea in ideas[:3]:
                    preview_lines.append(f"- {idea}")
                await self._safe_reply(message, "\n".join(preview_lines))
            except Exception:
                pass

            await self._reply_json(message, shaped)

        logger.info("reply_json_sent", extra={"cid": correlation_id, "request_id": req_id})

    async def _handle_forward_flow(
        self, message: Any, *, correlation_id: str | None = None, interaction_id: int | None = None
    ) -> None:
        text = (getattr(message, "text", None) or getattr(message, "caption", "") or "").strip()
        title = getattr(getattr(message, "forward_from_chat", None), "title", "")
        prompt = f"Channel: {title}\n\n{text}"
        # Optional normalization for forwards as well
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                prompt = normalize_with_textacy(prompt)
        except Exception:
            pass

        # Create request row (pending)
        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

        fwd_chat_obj = getattr(message, "forward_from_chat", None)
        fwd_from_chat_id_raw = getattr(fwd_chat_obj, "id", 0) if fwd_chat_obj is not None else None
        fwd_from_chat_id = int(fwd_from_chat_id_raw) if fwd_from_chat_id_raw is not None else None

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        fwd_from_msg_id = int(fwd_msg_id_raw) if fwd_msg_id_raw is not None else None

        req_id = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_message_id=input_message_id,
            fwd_from_chat_id=fwd_from_chat_id,
            fwd_from_msg_id=fwd_from_msg_id,
            route_version=1,
        )

        # Snapshot telegram message
        try:
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e)})

        # Notify: request accepted (forward)
        try:
            await self._safe_reply(message, "Accepted. Generating summary...")
        except Exception:
            pass

        # Language detection and choice
        detected = detect_language(text)
        try:
            self.db.update_request_lang_detected(req_id, detected)
        except Exception as e:  # noqa: BLE001
            logger.error("persist_lang_detected_error", extra={"error": str(e)})
        chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
        system_prompt = await self._load_system_prompt(chosen_lang)
        logger.debug(
            "language_choice",
            extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
        )
        # Notify: language detected (forward)
        try:
            await self._safe_reply(
                message,
                f"Language detected: {detected or 'unknown'}. Sending to LLM...",
            )
        except Exception:
            pass

        # LLM - truncate content if too long
        max_content_length = 45000  # Leave some buffer for the prompt
        if len(prompt) > max_content_length:
            prompt = prompt[:max_content_length] + "\n\n[Content truncated due to length]"
            logger.warning(
                "content_truncated",
                extra={
                    "original_length": len(prompt),
                    "truncated_length": max_content_length,
                    "cid": correlation_id,
                },
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Summarize the following message to the specified JSON schema. "
                    f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n{prompt}"
                ),
            },
        ]
        async with self._ext_sem:
            llm = await self._openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=self.cfg.openrouter.max_tokens,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
            )
        # Notify: LLM finished (forward)
        try:
            await self._safe_reply(
                message,
                (
                    "LLM call finished"
                    f" ({'ok' if llm.status == 'ok' else 'error'}, {llm.latency_ms or 0} ms)."
                ),
            )
        except Exception:
            pass
        if llm.status != "ok" or not llm.response_text:
            # persist LLM call as error, then reply
            try:
                self.db.insert_llm_call(
                    request_id=req_id,
                    provider="openrouter",
                    model=llm.model or self.cfg.openrouter.model,
                    endpoint=llm.endpoint,
                    request_headers_json=json.dumps(llm.request_headers or {}),
                    request_messages_json=json.dumps(llm.request_messages or []),
                    response_text=llm.response_text,
                    response_json=json.dumps(llm.response_json or {}),
                    tokens_prompt=llm.tokens_prompt,
                    tokens_completion=llm.tokens_completion,
                    cost_usd=llm.cost_usd,
                    latency_ms=llm.latency_ms,
                    status=llm.status,
                    error_text=llm.error_text,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})
            self.db.update_request_status(req_id, "error")
            await self._safe_reply(message, f"LLM error. Error ID: {correlation_id}")
            logger.error("openrouter_error", extra={"error": llm.error_text, "cid": correlation_id})
            try:
                self._audit(
                    "ERROR",
                    "openrouter_error",
                    {"request_id": req_id, "cid": correlation_id, "error": llm.error_text},
                )
            except Exception:
                pass

            # Update interaction with error
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=f"LLM error: {llm.error_text or 'Unknown error'}",
                    request_id=req_id,
                )
            return

        try:
            raw = llm.response_text.strip().strip("` ")
            summary_json = json.loads(raw)
        except Exception:
            start = llm.response_text.find("{")
            end = llm.response_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                # Attempt one repair using assistant prefill best-practice
                try:
                    logger.info("json_repair_attempt", extra={"cid": correlation_id})
                    repair_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "assistant", "content": llm.response_text},
                        {
                            "role": "user",
                            "content": (
                                "Your previous message was not a valid JSON object. "
                                "Respond with ONLY a corrected JSON that matches the schema exactly."
                            ),
                        },
                    ]
                    async with self._ext_sem:
                        repair = await self._openrouter.chat(
                            repair_messages,
                            temperature=self.cfg.openrouter.temperature,
                            max_tokens=self.cfg.openrouter.max_tokens,
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                        )
                    if repair.status == "ok" and repair.response_text:
                        try:
                            summary_json = json.loads(repair.response_text.strip().strip("` "))
                        except Exception:
                            rs = repair.response_text.find("{")
                            re_ = repair.response_text.rfind("}")
                            if rs != -1 and re_ != -1 and re_ > rs:
                                summary_json = json.loads(repair.response_text[rs : re_ + 1])
                            else:
                                raise ValueError("repair_failed")
                    else:
                        raise ValueError("repair_call_error")
                except Exception:
                    self.db.update_request_status(req_id, "error")
                    await self._safe_reply(
                        message, f"Invalid summary format. Error ID: {correlation_id}"
                    )

                    # Update interaction with error
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="error",
                            error_occurred=True,
                            error_message="Invalid summary format",
                            request_id=req_id,
                        )
                    return
            else:
                summary_json = json.loads(llm.response_text[start : end + 1])

        shaped = validate_and_shape_summary(summary_json)
        try:
            self.db.insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=json.dumps(llm.request_headers or {}),
                request_messages_json=json.dumps([m for m in messages]),
                response_text=llm.response_text,
                response_json=json.dumps(llm.response_json or {}),
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})

        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(shaped)
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        # Update interaction with successful completion
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

        # Quick human-friendly preview before JSON (best-practice feedback)
        try:
            preview_lines = [
                "TL;DR:",
                str(shaped.get("summary_250", "")).strip(),
            ]
            tags = shaped.get("topic_tags") or []
            if tags:
                preview_lines.append("Tags: " + " ".join(tags[:6]))
            ideas = [str(x).strip() for x in (shaped.get("key_ideas") or []) if str(x).strip()]
            for idea in ideas[:3]:
                preview_lines.append(f"- {idea}")
            await self._safe_reply(message, "\n".join(preview_lines))
        except Exception:
            pass

        await self._reply_json(message, shaped)

    async def _reply_json(self, message: Any, obj: dict) -> None:
        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        # Send large JSON as a file to avoid Telegram message size limits
        if len(pretty) > 3500:
            try:
                bio = io.BytesIO(pretty.encode("utf-8"))
                bio.name = "summary.json"
                msg_any: Any = message
                await msg_any.reply_document(bio, caption="Summary JSON")
                return
            except Exception as e:  # noqa: BLE001
                logger.error("reply_document_failed", extra={"error": str(e)})
        await self._safe_reply(message, f"```\n{pretty}\n```")

    async def _safe_reply(self, message: Any, text: str, *, parse_mode: str | None = None) -> None:
        try:
            msg_any: Any = message
            if parse_mode:
                await msg_any.reply_text(text, parse_mode=parse_mode)
            else:
                await msg_any.reply_text(text)
            try:
                logger.debug("reply_text_sent", extra={"length": len(text)})
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.error("reply_failed", extra={"error": str(e)})

    def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        # Security: Validate request_id
        if not isinstance(request_id, int) or request_id <= 0:
            raise ValueError("Invalid request_id")

        # Security: Validate message object
        if message is None:
            raise ValueError("Message cannot be None")

        # Extract basic fields with best-effort approach
        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        msg_id = int(msg_id_raw) if msg_id_raw is not None else None

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        def _to_epoch(val: Any) -> int | None:
            try:
                if isinstance(val, datetime):
                    return int(val.timestamp())
                if val is None:
                    return None
                # Some libraries expose pyrogram types with .timestamp or int-like
                if hasattr(val, "timestamp"):
                    try:
                        ts_val = getattr(val, "timestamp")
                        if callable(ts_val):
                            return int(ts_val())
                    except Exception:
                        pass
                return int(val)  # may raise if not int-like
            except Exception:
                return None

        date_ts = _to_epoch(
            getattr(message, "date", None) or getattr(message, "forward_date", None)
        )
        text_full = getattr(message, "text", None) or getattr(message, "caption", "") or None

        # Entities
        entities_obj = list(getattr(message, "entities", []) or [])
        entities_obj.extend(list(getattr(message, "caption_entities", []) or []))
        try:

            def _ent_to_dict(e: Any) -> dict:
                if hasattr(e, "to_dict"):
                    try:
                        return e.to_dict()
                    except Exception:
                        pass
                return getattr(e, "__dict__", {})

            entities_json = json.dumps([_ent_to_dict(e) for e in entities_obj], ensure_ascii=False)
        except Exception:
            entities_json = None

        media_type = None
        media_file_ids: list[str] = []
        # Detect common media types and collect file_ids
        try:
            if getattr(message, "photo", None) is not None:
                media_type = "photo"
                photo = getattr(message, "photo")
                fid = getattr(photo, "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "video", None) is not None:
                media_type = "video"
                fid = getattr(getattr(message, "video"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "document", None) is not None:
                media_type = "document"
                fid = getattr(getattr(message, "document"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "audio", None) is not None:
                media_type = "audio"
                fid = getattr(getattr(message, "audio"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "voice", None) is not None:
                media_type = "voice"
                fid = getattr(getattr(message, "voice"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "animation", None) is not None:
                media_type = "animation"
                fid = getattr(getattr(message, "animation"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "sticker", None) is not None:
                media_type = "sticker"
                fid = getattr(getattr(message, "sticker"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
        except Exception:
            pass
        media_file_ids_json = (
            json.dumps(media_file_ids, ensure_ascii=False) if media_file_ids else None
        )

        # Forward info
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_chat_id_raw = getattr(fwd_chat, "id", 0) if fwd_chat is not None else None
        forward_from_chat_id = int(fwd_chat_id_raw) if fwd_chat_id_raw is not None else None
        forward_from_chat_type = getattr(fwd_chat, "type", None)
        forward_from_chat_title = getattr(fwd_chat, "title", None)

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        forward_from_message_id = int(fwd_msg_id_raw) if fwd_msg_id_raw is not None else None
        forward_date_ts = _to_epoch(getattr(message, "forward_date", None))

        # Raw JSON if possible
        raw_json = None
        try:
            if hasattr(message, "to_dict"):
                raw_json = json.dumps(message.to_dict(), ensure_ascii=False)
            else:
                raw_json = None
        except Exception:
            raw_json = None

        self.db.insert_telegram_message(
            request_id=request_id,
            message_id=msg_id,
            chat_id=chat_id,
            date_ts=date_ts,
            text_full=text_full,
            entities_json=entities_json,
            media_type=media_type,
            media_file_ids_json=media_file_ids_json,
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_type=forward_from_chat_type,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            forward_date_ts=forward_date_ts,
            telegram_raw_json=raw_json,
        )

    def _audit(self, level: str, event: str, details: dict) -> None:
        try:
            self.db.insert_audit_log(
                level=level, event=event, details_json=json.dumps(details, ensure_ascii=False)
            )
        except Exception as e:  # noqa: BLE001
            logger.error("audit_persist_failed", extra={"error": str(e), "event": event})

    async def _load_system_prompt(self, lang: str) -> str:
        # Load prompt file based on language
        from pathlib import Path

        base = Path(__file__).resolve().parents[1] / "prompts"
        fname = "summary_system_ru.txt" if lang == LANG_RU else "summary_system_en.txt"
        path = base / fname
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            # Fallback inline prompt
            return "You are a precise assistant that returns only a strict JSON object matching the provided schema."

    def _is_affirmative(self, text: str) -> bool:
        t = text.strip().lower()
        return t in {"y", "yes", "+", "ok", "okay", "sure", "да", "ага", "угу", "👍", "✅"}

    def _is_negative(self, text: str) -> bool:
        t = text.strip().lower()
        return t in {"n", "no", "-", "cancel", "stop", "нет", "не"}

    def _log_user_interaction(
        self,
        *,
        user_id: int,
        chat_id: int | None = None,
        message_id: int | None = None,
        interaction_type: str,
        command: str | None = None,
        input_text: str | None = None,
        input_url: str | None = None,
        has_forward: bool = False,
        forward_from_chat_id: int | None = None,
        forward_from_chat_title: str | None = None,
        forward_from_message_id: int | None = None,
        media_type: str | None = None,
        entities_json: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Log a user interaction and return the interaction ID."""
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_log_placeholder",
            extra={
                "user_id": user_id,
                "interaction_type": interaction_type,
                "cid": correlation_id,
            },
        )
        return 0

    def _update_user_interaction(
        self,
        *,
        interaction_id: int,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        """Update an existing user interaction record."""
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_update_placeholder",
            extra={"interaction_id": interaction_id},
        )


# Route versioning constants
URL_ROUTE_VERSION = 1
FORWARD_ROUTE_VERSION = 1


async def idle() -> None:
    # Simple idle loop to keep the client running
    try:
        while True:  # noqa: ASYNC110
            await asyncio.sleep(3600)
    except asyncio.CancelledError:  # pragma: no cover
        return
