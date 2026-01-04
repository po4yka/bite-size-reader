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
from app.services.topic_search_utils import ensure_mapping

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.database import Database
    from app.services.embedding_service import EmbeddingService
    from app.services.hybrid_search_service import HybridSearchService
    from app.services.vector_search_service import VectorSearchService

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
        container: Any | None = None,
        hybrid_search: HybridSearchService | None = None,
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
        self._container = container
        self.hybrid_search = hybrid_search

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
            # Use hexagonal architecture use case for local search if available
            if (
                self._container is not None
                and formatter_source == "library"
                and isinstance(searcher, LocalTopicSearchService)
            ):
                from app.application.use_cases.search_topics import SearchTopicsQuery

                # Use the use case for local topic search
                query = SearchTopicsQuery(
                    topic=topic,
                    user_id=uid,
                    max_results=getattr(searcher, "max_results", 5),
                    correlation_id=correlation_id,
                )
                use_case = self._container.search_topics_use_case()
                if use_case is not None:
                    topic_articles = await use_case.execute(query)

                    # Convert TopicArticleDTO to format expected by formatter
                    results = []
                    for article in topic_articles:
                        results.append(
                            {
                                "request_id": article.request_id,
                                "url": article.url,
                                "title": article.title,
                                "created_at": article.created_at.isoformat()
                                if article.created_at
                                else None,
                                "relevance_score": article.relevance_score,
                                "matched_topics": article.matched_topics,
                            }
                        )
                else:
                    # Fallback if use case unavailable
                    results = await searcher.find_articles(topic, correlation_id=correlation_id)  # type: ignore[assignment]
            else:
                # Use the service directly for online search or if container unavailable
                results = await searcher.find_articles(topic, correlation_id=correlation_id)  # type: ignore[assignment]
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
            message,
            topic=topic,
            articles=results,  # type: ignore[arg-type]
            source=formatter_source,
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
            # Create inline keyboard buttons for confirmation
            buttons = [
                {"text": "✅ Yes", "callback_data": "multi_confirm_yes"},
                {"text": "❌ No", "callback_data": "multi_confirm_no"},
            ]
            keyboard = self.response_formatter.create_inline_keyboard(buttons)
            await self.response_formatter.safe_reply(
                message, f"Process {len(urls)} links?", reply_markup=keyboard
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
            awaiting_cancelled, multi_cancelled = await self.url_handler.cancel_pending_requests(
                uid
            )

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
        had_mention = bool(tokens and tokens[0].startswith("@"))
        if tokens and tokens[0].startswith("@"):
            tokens = tokens[1:]

        if not tokens:
            return 5, None

        max_limit = 20
        limit = 5
        topic_tokens: list[tuple[str, bool]] = []
        explicit_limit_set = False

        for raw_token in tokens:
            token = raw_token.strip()
            if not token:
                continue

            lowered = token.casefold()
            if lowered.startswith("limit=") or lowered.startswith("limit:"):
                candidate = token.split("=", 1)[-1] if "=" in token else token.split(":", 1)[-1]
                try:
                    parsed = int(candidate)
                except ValueError:
                    topic_tokens.append((token, False))
                    continue
                limit = max(1, min(parsed, max_limit))
                explicit_limit_set = True
                continue

            topic_tokens.append((token, token.isdigit()))

        if not explicit_limit_set and topic_tokens:
            candidate_index = len(topic_tokens) - 1
            if candidate_index >= 0 and topic_tokens[candidate_index][1]:
                candidate_token = topic_tokens[candidate_index][0]
                try:
                    parsed_limit = int(candidate_token)
                except ValueError:
                    pass
                else:
                    if parsed_limit <= max_limit:
                        has_non_digit_before = any(
                            not is_digit for _, is_digit in topic_tokens[:candidate_index]
                        )
                        if had_mention or has_non_digit_before:
                            limit = max(1, min(parsed_limit, max_limit))
                            del topic_tokens[candidate_index]

        topic = " ".join(token for token, _ in topic_tokens).strip() or None
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
            # Use hexagonal architecture use case if available
            if self._container is not None:
                from app.application.dto.summary_dto import SummaryDTO
                from app.application.use_cases.get_unread_summaries import GetUnreadSummariesQuery

                # Use the use case with topic filtering support
                query = GetUnreadSummariesQuery(
                    user_id=uid,
                    chat_id=chat_id,
                    limit=limit,
                    topic=topic,
                )
                use_case = self._container.get_unread_summaries_use_case()
                domain_summaries = await use_case.execute(query)

                # Convert domain models to database format for compatibility
                unread_summaries = []
                for summary in domain_summaries:
                    unread_summaries.append(
                        {
                            "request_id": summary.request_id,
                            "input_url": "Unknown URL",  # Not available in domain model
                            "created_at": summary.created_at.isoformat()
                            if hasattr(summary, "created_at") and summary.created_at
                            else "Unknown date",
                            "json_payload": summary.content,
                            "is_read": summary.is_read,
                            "id": summary.id,
                        }
                    )
            else:
                # Fallback to direct database access if container not available
                unread_summaries = self.db.get_unread_summaries(
                    user_id=uid,
                    chat_id=chat_id,
                    limit=limit,
                    topic=topic,
                )

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
                    metadata = ensure_mapping(payload.get("metadata"))
                    title = metadata.get("title") or payload.get("title") or input_url
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

            # Mark as read using hexagonal architecture if available
            if self._container is not None:
                from app.application.use_cases.mark_summary_as_read import MarkSummaryAsReadCommand

                summary_id = summary.get("id")
                if summary_id:
                    # Use the use case for marking as read
                    command = MarkSummaryAsReadCommand(
                        summary_id=summary_id,
                        user_id=uid,
                    )
                    use_case = self._container.mark_summary_as_read_use_case()
                    event = await use_case.execute(command)

                    # Publish the event to trigger side effects (analytics, audit log, etc.)
                    event_bus = self._container.event_bus()
                    await event_bus.publish(event)
                else:
                    # Fallback to direct database access if summary_id not available
                    self.db.mark_summary_as_read(request_id)
            else:
                # Fallback to direct database access if container not available
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

    async def handle_search_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /search command - hybrid semantic + keyword search."""
        chat_id = getattr(getattr(message, "chat", None), "id", None)
        logger.info(
            "command_search",
            extra={"uid": uid, "chat_id": chat_id, "cid": correlation_id, "text": text[:100]},
        )
        try:
            self._audit(
                "INFO",
                "command_search",
                {"uid": uid, "chat_id": chat_id, "cid": correlation_id, "text": text[:100]},
            )
        except Exception:
            pass

        # Check if search service is available
        if not self.hybrid_search:
            await self.response_formatter.safe_reply(
                message, "⚠️ Semantic search is currently unavailable."
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="search_disabled",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        # Extract query from command
        parts = text.split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""

        if not query:
            usage_msg = (
                "❌ Usage: `/search <query>`\n\n"
                "**Examples:**\n"
                "• `/search machine learning`\n"
                "• `/search python async programming`\n"
                "• `/search AI ethics`\n\n"
                "💡 **Features:**\n"
                "• Semantic vector search\n"
                "• Keyword (FTS) search\n"
                "• Query expansion with synonyms\n"
                "• Hybrid scoring for best results"
            )
            await self.response_formatter.safe_reply(message, usage_msg)
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="search_usage",
                    start_time=start_time,
                    logger_=logger,
                )
            return

        # Send searching message
        await self.response_formatter.safe_reply(message, f"🔍 Searching for: **{query}**...")

        try:
            # Perform hybrid search with all advanced features
            results = await self.hybrid_search.search(
                query=query,
                correlation_id=correlation_id,
            )

            if not results:
                await self.response_formatter.safe_reply(
                    message,
                    f"📭 No articles found for **{query}**.\n\n"
                    "💡 Try:\n"
                    "• Broader search terms\n"
                    "• Different keywords\n"
                    "• Check `/find` for online search",
                )
                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.db,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="search_empty",
                        start_time=start_time,
                        logger_=logger,
                    )
                return

            # Format and send results
            await self._send_search_results(message, query, results)

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="search_results",
                    start_time=start_time,
                    logger_=logger,
                )

        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_search_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Search failed. Please try again later or check bot logs for details.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="search_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )

    async def _send_search_results(
        self,
        message: Any,
        query: str,
        results: list,
    ) -> None:
        """Format and send search results to user."""
        # Build results message
        response_lines = [
            f"🎯 **Search Results** for: **{query}**",
            f"📊 Found {len(results)} article(s)\n",
        ]

        for i, result in enumerate(results[:10], 1):  # Limit to top 10 for Telegram
            title = result.title or result.url or "Untitled"
            url = result.url or ""
            snippet = result.snippet or ""

            # Truncate long titles and snippets for readability
            if len(title) > 100:
                title = title[:97] + "..."
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."

            result_text = f"{i}. **{title}**"
            if url:
                result_text += f"\n   🔗 {url}"
            if snippet:
                result_text += f"\n   📝 {snippet}"

            # Add source and date if available
            metadata_parts = []
            if result.source:
                metadata_parts.append(f"📰 {result.source}")
            if result.published_at:
                metadata_parts.append(f"📅 {result.published_at}")
            if metadata_parts:
                result_text += f"\n   {' | '.join(metadata_parts)}"

            response_lines.append(result_text)

        response_lines.append("\n💡 **Tip:** Use `/read <request_id>` to view full summaries")

        await self.response_formatter.safe_reply(message, "\n\n".join(response_lines))

    async def handle_sync_karakeep_command(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Handle /sync_karakeep command - sync articles with Karakeep."""
        logger.info(
            "command_sync_karakeep",
            extra={"uid": uid, "cid": correlation_id, "text": text},
        )

        # Check if Karakeep is enabled
        if not self.cfg.karakeep.enabled:
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Karakeep sync is not enabled.\n\n"
                "Set `KARAKEEP_ENABLED=true` in your environment to enable.",
            )
            return

        if not self.cfg.karakeep.api_key:
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Karakeep API key not configured.\n\nSet `KARAKEEP_API_KEY` in your environment.",
            )
            return

        # Parse subcommand
        parts = text.strip().split(maxsplit=1)
        subcommand = parts[1].lower() if len(parts) > 1 else "run"

        if subcommand == "status":
            await self._handle_karakeep_status(message, uid, correlation_id)
        elif subcommand in ("run", "sync"):
            await self._handle_karakeep_sync(
                message, uid, correlation_id, interaction_id, start_time
            )
        else:
            await self.response_formatter.safe_reply(
                message,
                "📖 **Karakeep Sync Commands:**\n\n"
                "`/sync_karakeep` - Run bidirectional sync\n"
                "`/sync_karakeep status` - Show sync statistics\n",
            )

    async def _handle_karakeep_status(self, message: Any, uid: int, correlation_id: str) -> None:
        """Show Karakeep sync status."""
        from app.adapters.karakeep import KarakeepSyncService

        try:
            service = KarakeepSyncService(
                api_url=self.cfg.karakeep.api_url,
                api_key=self.cfg.karakeep.api_key,
                sync_tag=self.cfg.karakeep.sync_tag,
            )
            status = await service.get_sync_status()

            status_text = (
                "📊 **Karakeep Sync Status**\n\n"
                f"📤 BSR → Karakeep: {status['bsr_to_karakeep']} items\n"
                f"📥 Karakeep → BSR: {status['karakeep_to_bsr']} items\n"
                f"📈 Total synced: {status['total_synced']} items\n"
            )
            if status.get("last_sync_at"):
                status_text += f"🕐 Last sync: {status['last_sync_at']}\n"

            await self.response_formatter.safe_reply(message, status_text)

        except Exception as exc:
            logger.exception("karakeep_status_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(message, f"⚠️ Failed to get sync status: {exc}")

    async def _handle_karakeep_sync(
        self,
        message: Any,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Run Karakeep sync."""
        from app.adapters.karakeep import KarakeepSyncService

        # Send initial message
        await self.response_formatter.safe_reply(message, "🔄 Starting Karakeep sync...")

        try:
            service = KarakeepSyncService(
                api_url=self.cfg.karakeep.api_url,
                api_key=self.cfg.karakeep.api_key,
                sync_tag=self.cfg.karakeep.sync_tag,
            )

            result = await service.run_full_sync(user_id=uid)

            # Format result message
            result_text = (
                "✅ **Karakeep Sync Complete**\n\n"
                f"📤 **BSR → Karakeep:**\n"
                f"   • Synced: {result.bsr_to_karakeep.items_synced}\n"
                f"   • Skipped: {result.bsr_to_karakeep.items_skipped}\n"
                f"   • Failed: {result.bsr_to_karakeep.items_failed}\n\n"
                f"📥 **Karakeep → BSR:**\n"
                f"   • Synced: {result.karakeep_to_bsr.items_synced}\n"
                f"   • Skipped: {result.karakeep_to_bsr.items_skipped}\n"
                f"   • Failed: {result.karakeep_to_bsr.items_failed}\n\n"
                f"⏱ Duration: {result.total_duration_seconds:.1f}s"
            )

            # Add errors if any
            all_errors = result.bsr_to_karakeep.errors + result.karakeep_to_bsr.errors
            if all_errors:
                result_text += f"\n\n⚠️ **Errors ({len(all_errors)}):**\n"
                for err in all_errors[:5]:  # Show max 5 errors
                    result_text += f"• {err[:100]}...\n" if len(err) > 100 else f"• {err}\n"

            await self.response_formatter.safe_reply(message, result_text)

            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="karakeep_sync_complete",
                    start_time=start_time,
                    logger_=logger,
                )

        except Exception as exc:
            logger.exception("karakeep_sync_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(message, f"❌ Karakeep sync failed: {exc}")
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.db,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="karakeep_sync_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    start_time=start_time,
                    logger_=logger,
                )
