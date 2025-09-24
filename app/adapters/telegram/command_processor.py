"""Command processing for Telegram bot."""
# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls

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
    ) -> None:
        self.cfg = cfg
        self.response_formatter = response_formatter
        self.db = db
        self.url_processor = url_processor
        self.url_handler: URLHandler | None = url_handler
        self._audit = audit_func

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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="welcome",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="help",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="dbinfo_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return

        await self.response_formatter.send_db_overview(message, overview)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="dbinfo",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="dbverify_error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
            return

        await self.response_formatter.send_db_verification(message, verification)
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="dbverify",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="No URLs found",
                    processing_time_ms=int((time.time() - start_time) * 1000),
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
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="processing",
                processing_time_ms=int((time.time() - start_time) * 1000),
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    processing_time_ms=int((time.time() - start_time) * 1000),
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="awaiting_url",
                    processing_time_ms=int((time.time() - start_time) * 1000),
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
        if self.url_handler is not None:
            awaiting_cancelled, multi_cancelled = self.url_handler.cancel_pending_requests(uid)

        if awaiting_cancelled and multi_cancelled:
            reply_text = "🛑 Cancelled your pending URL request and multi-link confirmation."
        elif awaiting_cancelled:
            reply_text = "🛑 Cancelled your pending URL request."
        elif multi_cancelled:
            reply_text = "🛑 Cancelled your pending multi-link confirmation."
        else:
            reply_text = "ℹ️ No pending link requests to cancel."

        await self.response_formatter.safe_reply(message, reply_text)

        if interaction_id:
            response_type = (
                "cancelled" if (awaiting_cancelled or multi_cancelled) else "cancel_none"
            )
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type=response_type,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

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
            extra={"interaction_id": interaction_id, "response_type": response_type},
        )

    async def handle_unread_command(
        self, message: Any, uid: int, correlation_id: str, interaction_id: int, start_time: float
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

        try:
            # Get unread summaries
            unread_summaries = self.db.get_unread_summaries(limit=5)

            if not unread_summaries:
                await self.response_formatter.safe_reply(
                    message, "📖 No unread articles found. All caught up!"
                )
                return

            # Send a message with the list of unread articles
            response_lines = ["📚 **Unread Articles:**"]
            for i, summary in enumerate(unread_summaries, 1):
                request_id = summary.get("request_id")
                input_url = summary.get("input_url", "Unknown URL")
                created_at = summary.get("created_at", "Unknown date")

                # Extract title from metadata if available
                json_payload = summary.get("json_payload", "{}")
                try:
                    payload = json.loads(json_payload) if json_payload else {}
                    title = payload.get("metadata", {}).get("title", input_url)
                except (json.JSONDecodeError, TypeError):
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
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="unread_list",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_unread_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to retrieve unread articles right now. Check bot logs for details.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    processing_time_ms=int((time.time() - start_time) * 1000),
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
            json_payload = summary.get("json_payload", "{}")
            try:
                shaped = json.loads(json_payload) if json_payload else {}
            except json.JSONDecodeError:
                await self.response_formatter.safe_reply(
                    message, f"❌ Error reading article data for ID `{request_id}`."
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
                await self.response_formatter.send_enhanced_summary_response(
                    message, shaped, llm_stub
                )

            # Send additional insights if available
            insights_json = summary.get("insights_json")
            if insights_json:
                try:
                    insights = json.loads(insights_json)
                    if insights:
                        await self.response_formatter.send_additional_insights_message(
                            message, insights, correlation_id
                        )
                except json.JSONDecodeError:
                    logger.warning(
                        "insights_decode_failed",
                        extra={"request_id": request_id, "cid": correlation_id},
                    )

            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="read_article",
                    request_id=request_id,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

        except Exception as exc:  # noqa: BLE001 - defensive catch
            logger.exception("command_read_failed", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(
                message,
                "⚠️ Unable to read the article right now. Check bot logs for details.",
            )
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=str(exc)[:500],
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )
