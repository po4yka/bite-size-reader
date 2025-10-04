"""Command processing for Telegram bot."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.task_manager import UserTaskManager
from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls
from app.db.user_interactions import async_safe_update_user_interaction
from app.services.topic_search import LocalTopicSearchService, TopicSearchService

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.database import Database

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Handles bot command processing."""

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
        db: Database,
        url_processor: URLProcessor,
        audit_func: Callable[[str, str, dict], None],
        url_handler: URLHandler | None = None,
        topic_searcher: TopicSearchService | None = None,
        local_searcher: LocalTopicSearchService | None = None,
        task_manager: UserTaskManager | None = None,
    ) -> None:
        self.cfg = cfg
        self.response_formatter = response_formatter
        self.db = db
        self.url_processor = url_processor
        self.url_handler: URLHandler | None = url_handler
        self._audit = audit_func
        self.topic_searcher = topic_searcher
        self.local_searcher = local_searcher
        self._task_manager = task_manager

    @staticmethod
    def _maybe_load_json(payload: Any) -> Any:
        if payload is None:
            return None
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, bytes | bytearray):
            try:
                payload = payload.decode("utf-8")
            except Exception:
                payload = payload.decode("utf-8", errors="replace")
        if isinstance(payload, str):
            stripped = payload.strip()
            if not stripped:
                return None
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return None
        return payload

    async def handle_start_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /start command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_start",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_start", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_welcome(message)
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="welcome",
                start_time=start_time,
                logger_=logger,
            )

    async def handle_help_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /help command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_help",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_help", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        await self.response_formatter.send_help(message)
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="help",
                start_time=start_time,
                logger_=logger,
            )

    async def handle_dbinfo_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /dbinfo command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_dbinfo",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_dbinfo", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        try:
            overview = self.db.get_database_overview()
        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_dbinfo_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to read database overview right now. Check bot logs for details.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="dbinfo_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
            return

        await self.response_formatter.send_db_overview(message, overview)
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="dbinfo",
                start_time=start_time,
                logger_=logger,
            )

    async def handle_dbverify_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
    ) -> None:
        """Handle /dbverify command."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_dbverify",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_dbverify", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        try:
            verification = self.db.verify_processing_integrity()
        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_dbverify_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to verify database records right now. Check bot logs for details.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="dbverify_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
            return

        await self.response_formatter.send_db_verification(message, verification)
        posts_info = verification.get("posts") if isinstance(verification, dict) else None
        reprocess_entries = posts_info.get("reprocess") if isinstance(posts_info, dict) else []

        if reprocess_entries:
            urls_to_process: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []

            for entry in reprocess_entries:
                if not isinstance(entry, dict):
                    continue
                req_type = str(entry.get("type") or "").lower()
                if req_type == "url":
                    url = entry.get("normalized_url") or entry.get("input_url")
                    if not url:
                        skipped.append(entry)
                        continue
                    urls_to_process.append(
                        {
                            "request_id": entry.get("request_id"),
                            "url": url,
                            "reasons": entry.get("reasons") or [],
                        }
                    )
                else:
                    skipped.append(entry)

            if urls_to_process or skipped:
                await self.response_formatter.send_db_reprocess_start(
                    message, url_targets=urls_to_process, skipped=skipped
                )

            failures: list[dict[str, Any]] = []
            for target in urls_to_process:
                url = target["url"]
                req_id = target.get("request_id")
                per_link_cid = generate_correlation_id()
                logger.info(
                    "dbverify_reprocess_start",
                    extra={
                        "request_id": req_id,
                        "url": url,
                        "cid": per_link_cid,
                        "cid_parent": correlation_id,
                    },
                )
                try:
                    await self.url_processor.handle_url_flow(
                        message,
                        url,
                        correlation_id=per_link_cid,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "dbverify_reprocess_failed",
                        extra={
                            "request_id": req_id,
                            "url": url,
                            "cid": per_link_cid,
                            "cid_parent": correlation_id,
                        },
                    )
                    failure_entry = dict(target)
                    failure_entry["error"] = str(exc)
                    failures.append(failure_entry)

            if urls_to_process or skipped:
                await self.response_formatter.send_db_reprocess_complete(
                    message,
                    url_targets=urls_to_process,
                    failures=failures,
                    skipped=skipped,
                )

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="dbverify",
                start_time=start_time,
                logger_=logger,
            )

    async def handle_find_online_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        *,
        command: str,
    ) -> None:
        """Handle Firecrawl-backed search commands."""

        await self._handle_topic_search(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
            command=command,
            searcher=self.topic_searcher,
            unavailable_message="⚠️ Online article search is currently unavailable.",
            usage_example="❌ Usage: `{cmd} <topic>`\n\nExample: `{cmd} Android System Design`",
            invalid_message="❌ Topic must contain visible characters. Try `{cmd} space exploration`.",
            error_message="⚠️ Unable to search online articles right now. Please try again later.",
            empty_message="No recent online articles found for **{topic}**.",
            response_prefix="topic_search_online",
            log_event="command_find_online",
            formatter_source="online",
        )

    async def handle_find_local_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        *,
        command: str,
    ) -> None:
        """Handle database-only topic search commands."""

        await self._handle_topic_search(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
            command=command,
            searcher=self.local_searcher,
            unavailable_message="⚠️ Library search is currently unavailable.",
            usage_example="❌ Usage: `{cmd} <topic>`\n\nExample: `{cmd} Android System Design`",
            invalid_message="❌ Topic must contain visible characters. Try `{cmd} space exploration`.",
            error_message="⚠️ Unable to search saved articles right now. Please try again later.",
            empty_message="No saved summaries matched **{topic}**.",
            response_prefix="topic_search_local",
            log_event="command_find_local",
            formatter_source="library",
        )

    async def _handle_topic_search(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        *,
        command: str,
        searcher: TopicSearchService | LocalTopicSearchService | None,
        unavailable_message: str,
        usage_example: str,
        invalid_message: str,
        error_message: str,
        empty_message: str,
        response_prefix: str,
        log_event: str,
        formatter_source: str,
    ) -> None:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            log_event,
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
                "text": text[:100],
            },
        )
        try:
            self._audit(
                "INFO",
                log_event,
                {"uid": uid, "chat_id": chat_id, "cid": correlation_id, "text": text[:100]},
            )
        except Exception:
            pass

        if not searcher:
            await self.response_formatter.safe_reply(message, unavailable_message)
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type=f"{response_prefix}_disabled",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        parts = text.split(maxsplit=1)
        topic = parts[1].strip() if len(parts) > 1 else ""
        if not topic:
            usage = usage_example.format(cmd=command)
            await self.response_formatter.safe_reply(message, usage)
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type=f"{response_prefix}_usage",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        try:
            results = await searcher.find_articles(topic, correlation_id=correlation_id)
        except ValueError:
            invalid = invalid_message.format(cmd=command)
            await self.response_formatter.safe_reply(message, invalid)
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type=f"{response_prefix}_invalid",
                    start_time=start_time,
                    logger_=logger,
                )
            return
        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception(f"{log_event}_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(message, error_message)
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type=f"{response_prefix}_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
            return

        if not results:
            await self.response_formatter.safe_reply(message, empty_message.format(topic=topic))
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type=f"{response_prefix}_empty",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        await self.response_formatter.send_topic_search_results(
            message, topic=topic, articles=results, source=formatter_source
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type=f"{response_prefix}_results",
                start_time=start_time,
                logger_=logger,
            )

    async def handle_summarize_all_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /summarize_all command."""
        urls = extract_all_urls(text)
        if len(urls) == 0:
            await self.response_formatter.safe_reply(
                message,
                "Send multiple URLs in one message after /summarize_all, separated by space or new line.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="No URLs found",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        chat_id = getattr(getattr(message, "chat", None), "id", None)
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

        await self.response_formatter.safe_reply(message, f"Processing {len(urls)} links...")
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="processing",
                start_time=start_time,
                logger_=logger,
            )

        for u in urls:
            per_link_cid = generate_correlation_id()
            logger.debug("processing_link", extra={"uid": uid, "url": u, "cid": per_link_cid})
            await self.url_processor.handle_url_flow(message, u, correlation_id=per_link_cid)

    async def handle_summarize_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> tuple[str | None, bool]:
        """Handle /summarize command. Returns (next_action, should_continue)."""
        urls = extract_all_urls(text)
        chat_id = getattr(getattr(message, "chat", None), "id", None)
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
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links? (yes/no)"
            )
            logger.debug("awaiting_multi_confirm", extra={"uid": uid, "count": len(urls)})
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    start_time=start_time,
                    logger_=logger,
                )
            return "multi_confirm", False
        elif len(urls) == 1:
            await self.url_processor.handle_url_flow(
                message,
                urls[0],
                correlation_id=correlation_id,
                interaction_id=interaction_id,
            )
            return None, False
        else:
            await self.response_formatter.safe_reply(message, "Send a URL to summarize.")
            logger.debug("awaiting_url", extra={"uid": uid})
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="awaiting_url",
                    start_time=start_time,
                    logger_=logger,
                )
            return "awaiting_url", False

    async def handle_cancel_command(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /cancel command to clear pending URL flows."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_cancel",
            extra={
                "uid": uid,
                "chat_id": chat_id,
                "cid": correlation_id,
            },
        )
        try:
            self._audit(
                "INFO",
                "command_cancel",
                {"uid": uid, "chat_id": chat_id, "cid": correlation_id},
            )
        except Exception:
            pass

        awaiting_cancelled = False
        multi_cancelled = False
        active_cancelled = 0
        if self.url_handler is not None:
            awaiting_cancelled, multi_cancelled = self.url_handler.cancel_pending_requests(uid)

        if self._task_manager is not None:
            active_cancelled = await self._task_manager.cancel(uid, exclude_current=True)

        cancelled_parts: list[str] = []
        if awaiting_cancelled:
            cancelled_parts.append("pending URL request")
        if multi_cancelled:
            cancelled_parts.append("pending multi-link confirmation")
        if active_cancelled:
            if active_cancelled == 1:
                cancelled_parts.append("ongoing request")
            else:
                cancelled_parts.append(f"{active_cancelled} ongoing requests")

        if cancelled_parts:
            if len(cancelled_parts) == 1:
                detail = cancelled_parts[0]
            else:
                detail = ", ".join(cancelled_parts[:-1]) + f", and {cancelled_parts[-1]}"
            reply_text = f"🛑 Cancelled your {detail}."
        else:
            reply_text = "ℹ️ No pending link requests to cancel."

        await self.response_formatter.safe_reply(message, reply_text)

        if interaction_id:
            response_type = (
                "cancelled"
                if (awaiting_cancelled or multi_cancelled or active_cancelled)
                else "cancel_none"
            )
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type=response_type,
                start_time=start_time,
                logger_=logger,
            )

    @staticmethod
    def _parse_unread_arguments(text: str | None) -> tuple[int, str | None]:
        """Parse optional limit and topic arguments from an /unread command string."""

        if not text:
            return 5, None

        remainder = text[len("/unread") :].strip() if text.startswith("/unread") else text
        if not remainder:
            return 5, None

        tokens = remainder.split()
        if tokens and tokens[0].startswith("@"):
            tokens = tokens[1:]

        if not tokens:
            return 5, None

        max_limit = 20
        limit = 5
        topic_parts: list[str] = []
        for raw_token in tokens:
            token = raw_token.strip()
            if not token:
                continue
            lowered = token.casefold()
            if lowered.startswith("limit=") or lowered.startswith("limit:"):
                candidate = token.split("=", 1)[-1] if "=" in token else token.split(":", 1)[-1]
            elif token.isdigit():
                candidate = token
            else:
                candidate = None

            if candidate is not None:
                try:
                    parsed = int(candidate)
                except ValueError:
                    topic_parts.append(token)
                    continue
                limit = max(1, min(parsed, max_limit))
                continue

            topic_parts.append(token)

        topic = " ".join(topic_parts).strip() or None
        return limit, topic

    async def handle_unread_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /unread command - retrieve unread articles."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_unread",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id},
        )
        try:
            self._audit(
                "INFO", "command_unread", {"uid": uid, "chat_id": chat_id, "cid": correlation_id}
            )
        except Exception:
            pass

        limit, topic = self._parse_unread_arguments(text)

        try:
            unread_summaries = self.db.get_unread_summaries(limit=limit, topic=topic)

            if not unread_summaries:
                if topic:
                    await self.response_formatter.safe_reply(
                        message,
                        f'📖 No unread articles found for topic "{topic}".',
                    )
                    return
                await self.response_formatter.safe_reply(
                    message, "📖 No unread articles found. All caught up!"
                )
                return

            # Send a message with the list of unread articles
            response_lines = ["📚 **Unread Articles:**"]
            if topic:
                response_lines.append(f"🔍 Topic filter: {topic}")
            if limit:
                response_lines.append(f"📦 Showing up to {limit} article(s)")
            for i, summary in enumerate(unread_summaries, 1):
                request_id = summary.get("request_id")
                input_url = summary.get("input_url", "Unknown URL")
                created_at = summary.get("created_at", "Unknown date")

                # Extract title from metadata if available
                payload = self._maybe_load_json(summary.get("json_payload"))
                if isinstance(payload, Mapping):
                    title = (
                        payload.get("metadata", {}).get("title")
                        or payload.get("title")
                        or input_url
                    )
                else:
                    title = input_url

                response_lines.append(
                    f"{i}. **{title}**\n"
                    f"   🔗 {input_url}\n"
                    f"   📅 {created_at}\n"
                    f"   🆔 Request ID: `{request_id}`"
                )

            response_lines.append(
                "\n💡 **Tip:** Send `/read <request_id>` to mark an article as read and view it."
            )

            await self.response_formatter.safe_reply(message, "\n".join(response_lines))

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="unread_list",
                    start_time=start_time,
                    logger_=logger,
                )

        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_unread_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to retrieve unread articles right now. Check bot logs for details.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )

    async def handle_read_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /read <request_id> command - mark article as read and send it."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_read",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id, "text": text[:100]},
        )
        try:
            self._audit(
                "INFO",
                "command_read",
                {"uid": uid, "chat_id": chat_id, "cid": correlation_id, "text": text[:100]},
            )
        except Exception:
            pass

        try:
            # Extract request_id from command text
            parts = text.split()
            if len(parts) < 2:
                await self.response_formatter.safe_reply(
                    message, "❌ Usage: `/read <request_id>`\n\nExample: `/read 123`"
                )
                return

            try:
                request_id = int(parts[1])
            except ValueError:
                await self.response_formatter.safe_reply(
                    message, "❌ Invalid request ID. Must be a number.\n\nExample: `/read 123`"
                )
                return

            # Get the unread summary
            summary = self.db.get_unread_summary_by_request_id(request_id)
            if not summary:
                await self.response_formatter.safe_reply(
                    message, f"❌ Article with ID `{request_id}` not found or already read."
                )
                return

            # Parse the summary payload
            payload = self._maybe_load_json(summary.get("json_payload"))
            if isinstance(payload, Mapping):
                shaped = dict(payload)
            else:
                shaped = {}
                if payload is not None:
                    await self.response_formatter.safe_reply(
                        message,
                        f"❌ Error reading article data for ID `{request_id}`.",
                    )
                    return

            # Mark as read
            self.db.mark_summary_as_read(request_id)

            # Send the article
            input_url = summary.get("input_url", "Unknown URL")
            await self.response_formatter.safe_reply(
                message, f"📖 **Reading Article** (ID: `{request_id}`)\n🔗 {input_url}"
            )

            # Send the summary
            if shaped:
                # Try to resolve model used for this request to avoid 'unknown' in header
                try:
                    model_name = self.db.get_latest_llm_model_by_request_id(request_id)
                except Exception:
                    model_name = None
                llm_stub = type("LLMStub", (), {"model": model_name})()
                await self.response_formatter.send_structured_summary_response(
                    message, shaped, llm_stub
                )

            # Send additional insights if available
            insights_raw = summary.get("insights_json")
            insights = self._maybe_load_json(insights_raw)
            if isinstance(insights, Mapping) and insights:
                await self.response_formatter.send_additional_insights_message(
                    message, dict(insights), correlation_id
                )

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="read_article",
                    request_id=request_id,
                    start_time=start_time,
                    logger_=logger,
                )

        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_read_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to read the article right now. Check bot logs for details.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
