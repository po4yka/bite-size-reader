from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.adapters.firecrawl_parser import FirecrawlClient
from app.adapters.openrouter_client import OpenRouterClient
from app.config import AppConfig
from app.core.lang import LANG_RU, choose_language, detect_language
from app.core.logging_utils import generate_correlation_id, setup_json_logging
from app.core.summary_contract import validate_and_shape_summary
from app.core.url_utils import extract_all_urls, looks_like_url, normalize_url, url_hash_sha256
from app.db.database import Database

try:
    from pyrogram import Client, filters
    from pyrogram.types import Message
except Exception:  # pragma: no cover - allow import in environments without deps
    Client = object  # type: ignore
    filters = None  # type: ignore
    Message = object  # type: ignore


logger = logging.getLogger(__name__)


@dataclass
class TelegramBot:
    cfg: AppConfig
    db: Database

    def __post_init__(self) -> None:  # type: ignore[override]
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

    async def start(self) -> None:
        if not self.client:
            logger.warning("telegram_client_not_available")
            return

        # Register handlers only if filters are available
        if filters:

            @self.client.on_message(filters.private)
            async def _handler(client: Client, message: Message):  # type: ignore[valid-type]
                await self._on_message(message)

        await self.client.start()  # type: ignore[union-attr]
        logger.info("bot_started")
        await self._setup_bot_commands()
        await idle()

    async def _on_message(self, message: Any) -> None:
        try:
            correlation_id = generate_correlation_id()
            # Owner-only gate
            uid = int(getattr(message.from_user, "id", 0))
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
                return

            text = (getattr(message, "text", None) or getattr(message, "caption", "") or "").strip()

            # Commands
            if text.startswith("/help") or text.startswith("/start"):
                await self._send_help(message)
                return

            if text.startswith("/summarize"):
                # If URL is in the same message, extract and process; otherwise set awaiting state
                urls = extract_all_urls(text)
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                elif len(urls) == 1:
                    await self._handle_url_flow(message, urls[0], correlation_id=correlation_id)
                else:
                    self._awaiting_url_users.add(uid)
                    await self._safe_reply(message, "Send a URL to summarize.")
                    logger.debug("awaiting_url", extra={"uid": uid})
                return

            # If awaiting a URL due to prior /summarize
            if uid in self._awaiting_url_users and looks_like_url(text):
                urls = extract_all_urls(text)
                self._awaiting_url_users.discard(uid)
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                    return
                if len(urls) == 1:
                    logger.debug("received_awaited_url", extra={"uid": uid})
                    await self._handle_url_flow(message, urls[0], correlation_id=correlation_id)
                    return

            if text and looks_like_url(text):
                urls = extract_all_urls(text)
                if len(urls) > 1:
                    self._pending_multi_links[uid] = urls
                    await self._safe_reply(message, f"Process {len(urls)} links? (yes/no)")
                    logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
                elif len(urls) == 1:
                    await self._handle_url_flow(message, urls[0], correlation_id=correlation_id)
                return

            # Handle yes/no responses for pending multi-link confirmation
            if uid in self._pending_multi_links:
                if self._is_affirmative(text):
                    urls = self._pending_multi_links.pop(uid)
                    await self._safe_reply(message, f"Processing {len(urls)} links...")
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
                    return

            if getattr(message, "forward_from_chat", None) and getattr(
                message, "forward_from_message_id", None
            ):
                await self._handle_forward_flow(message, correlation_id=correlation_id)
                return

            await self._safe_reply(message, "Send a URL or forward a channel post.")
            logger.debug(
                "unknown_input",
                extra={
                    "has_forward": bool(getattr(message, "forward_from_chat", None)),
                    "text_len": len(text),
                },
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

    async def _send_help(self, message: Any) -> None:
        help_text = (
            "Bite-Size Reader\n\n"
            "Commands:\n"
            "- /help — show this help.\n"
            "- /summarize <URL> — summarize a URL.\n\n"
            "Usage:\n"
            "- Send a URL, or forward a channel post to get a JSON summary.\n"
            "- You can also send /summarize and then a URL in the next message."
        )
        await self._safe_reply(message, help_text)

    async def _setup_bot_commands(self) -> None:
        if not self.client or Client is object:  # type: ignore[truthy-bool]
            return
        try:
            from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats  # type: ignore

            commands = [
                BotCommand("help", "Show help and usage"),
                BotCommand("summarize", "Summarize a URL (send URL next)"),
            ]
            try:
                await self.client.set_bot_commands(commands, scope=BotCommandScopeAllPrivateChats())  # type: ignore[attr-defined]
                logger.info("bot_commands_set", extra={"count": len(commands)})
            except Exception as e:  # noqa: BLE001
                logger.warning("bot_commands_set_failed", extra={"error": str(e)})
        except Exception:
            # Types not available; skip
            return

    async def _handle_url_flow(
        self, message: Any, url_text: str, *, correlation_id: str | None = None
    ) -> None:
        norm = normalize_url(url_text)
        dedupe = url_hash_sha256(norm)
        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm, "hash": dedupe, "cid": correlation_id},
        )
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
            req_id = self.db.create_request(
                type_="url",
                status="pending",
                correlation_id=correlation_id,
                chat_id=int(getattr(getattr(message, "chat", None), "id", 0)) or None,
                user_id=int(getattr(getattr(message, "from_user", None), "id", 0)) or None,
                input_url=url_text,
                normalized_url=norm,
                dedupe_hash=dedupe,
                input_message_id=int(getattr(message, "id", getattr(message, "message_id", 0)))
                or None,
                route_version=URL_ROUTE_VERSION,
            )

            # Snapshot telegram message (only on first request for this URL)
            try:
                self._persist_message_snapshot(req_id, message)
            except Exception as e:  # noqa: BLE001
                logger.error("snapshot_error", extra={"error": str(e), "cid": correlation_id})

        # Firecrawl or reuse existing crawl result
        existing_crawl = self.db.get_crawl_result_by_request(req_id)
        if existing_crawl and existing_crawl.get("content_markdown"):
            content_markdown = existing_crawl["content_markdown"]
            self._audit("INFO", "reuse_crawl_result", {"request_id": req_id, "cid": correlation_id})
        else:
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

            if crawl.status != "ok" or not crawl.content_markdown:
                self.db.update_request_status(req_id, "error")
                await self._safe_reply(
                    message,
                    f"Failed to fetch content. Error ID: {correlation_id}",
                )
                logger.error(
                    "firecrawl_error", extra={"error": crawl.error_text, "cid": correlation_id}
                )
                try:
                    self._audit(
                        "ERROR",
                        "firecrawl_error",
                        {"request_id": req_id, "cid": correlation_id, "error": crawl.error_text},
                    )
                except Exception:
                    pass
                return
            content_markdown = crawl.content_markdown or ""

        # Language detection and choice
        detected = detect_language(content_markdown or "")
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

        # LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Summarize the following content to the specified JSON schema. "
                    f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n{content_markdown}"
                ),
            },
        ]
        llm = await self._openrouter.chat(messages, request_id=req_id)
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

        if llm.status != "ok" or not llm.response_text:
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
            return

        # Best-effort parse + validate
        try:
            raw = llm.response_text.strip().strip("` ")
            summary_json = json.loads(raw)
        except Exception:
            start = llm.response_text.find("{")
            end = llm.response_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                self.db.update_request_status(req_id, "error")
                await self._safe_reply(
                    message, f"Invalid summary format. Error ID: {correlation_id}"
                )
                return
            summary_json = json.loads(llm.response_text[start : end + 1])

        shaped = validate_and_shape_summary(summary_json)
        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(shaped)
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})
        await self._reply_json(message, shaped)

    async def _handle_forward_flow(
        self, message: Any, *, correlation_id: str | None = None
    ) -> None:
        text = (getattr(message, "text", None) or getattr(message, "caption", "") or "").strip()
        title = getattr(getattr(message, "forward_from_chat", None), "title", "")
        prompt = f"Channel: {title}\n\n{text}"

        # Create request row (pending)
        req_id = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=correlation_id,
            chat_id=int(getattr(getattr(message, "chat", None), "id", 0)) or None,
            user_id=int(getattr(getattr(message, "from_user", None), "id", 0)) or None,
            input_message_id=int(getattr(message, "id", getattr(message, "message_id", 0))) or None,
            fwd_from_chat_id=int(getattr(getattr(message, "forward_from_chat", None), "id", 0))
            or None,
            fwd_from_msg_id=int(getattr(message, "forward_from_message_id", 0)) or None,
            route_version=1,
        )

        # Snapshot telegram message
        try:
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e)})

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
        llm = await self._openrouter.chat(messages, request_id=req_id)
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
            return

        try:
            raw = llm.response_text.strip().strip("` ")
            summary_json = json.loads(raw)
        except Exception:
            start = llm.response_text.find("{")
            end = llm.response_text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                self.db.update_request_status(req_id, "error")
                await self._safe_reply(
                    message, f"Invalid summary format. Error ID: {correlation_id}"
                )
                return
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
        await self._reply_json(message, shaped)

    async def _reply_json(self, message: Any, obj: dict) -> None:
        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        await self._safe_reply(message, f"```\n{pretty}\n```")

    async def _safe_reply(self, message: Any, text: str) -> None:
        try:
            await message.reply_text(text)  # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            logger.error("reply_failed", extra={"error": str(e)})

    def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        # Extract basic fields with best-effort approach
        msg_id = int(getattr(message, "id", getattr(message, "message_id", 0))) or None
        chat_id = int(getattr(getattr(message, "chat", None), "id", 0)) or None
        date_ts = int(getattr(message, "date", getattr(message, "forward_date", 0)) or 0) or None
        text_full = getattr(message, "text", None) or getattr(message, "caption", "") or None

        # Entities
        entities_obj = list(getattr(message, "entities", []) or [])
        entities_obj.extend(list(getattr(message, "caption_entities", []) or []))
        try:

            def _ent_to_dict(e: Any) -> dict:
                if hasattr(e, "to_dict"):
                    try:
                        return e.to_dict()  # type: ignore[attr-defined]
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
        forward_from_chat_id = int(getattr(fwd_chat, "id", 0)) or None
        forward_from_chat_type = getattr(fwd_chat, "type", None)
        forward_from_chat_title = getattr(fwd_chat, "title", None)
        forward_from_message_id = int(getattr(message, "forward_from_message_id", 0)) or None
        forward_date_ts = int(getattr(message, "forward_date", 0)) or None

        # Raw JSON if possible
        raw_json = None
        try:
            if hasattr(message, "to_dict"):
                raw_json = json.dumps(message.to_dict(), ensure_ascii=False)  # type: ignore[attr-defined]
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
