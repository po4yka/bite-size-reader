"""Callback handler for inline button interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import generate_correlation_id

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


# Callback data format: "action:summary_id:param"
# Examples:
#   "export:abc123:pdf"     - Export summary as PDF
#   "export:abc123:md"      - Export summary as Markdown
#   "export:abc123:html"    - Export summary as HTML
#   "translate:abc123"      - Translate summary to Russian
#   "similar:abc123"        - Find similar summaries
#   "save:abc123"           - Toggle bookmark/favorite
#   "rate:abc123:1"         - Rate summary (thumbs up)
#   "rate:abc123:-1"        - Rate summary (thumbs down)
#   "multi_confirm_yes"     - Confirm multi-link processing
#   "multi_confirm_no"      - Cancel multi-link processing


class CallbackHandler:
    """Handles inline button callback queries for post-summary actions."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_handler: URLHandler | None = None,
    ) -> None:
        self.db = db
        self.response_formatter = response_formatter
        self.url_handler = url_handler
        # Rate limit: track recent clicks per user (debounce)
        self._recent_clicks: dict[tuple[int, str], float] = {}
        self._click_cooldown_seconds = 1.0

    async def handle_callback(
        self,
        callback_query: Any,
        uid: int,
        callback_data: str,
    ) -> bool:
        """Route callback to appropriate handler.

        Returns:
            True if callback was handled, False otherwise
        """
        # Check debounce
        import time

        click_key = (uid, callback_data)
        now = time.time()
        last_click = self._recent_clicks.get(click_key, 0)
        if now - last_click < self._click_cooldown_seconds:
            logger.debug(
                "callback_debounced",
                extra={"uid": uid, "data": callback_data, "cooldown": self._click_cooldown_seconds},
            )
            return True  # Already handled, just debounce
        self._recent_clicks[click_key] = now

        # Cleanup old entries periodically (simple LRU-ish)
        if len(self._recent_clicks) > 1000:
            cutoff = now - 60  # Keep last 60 seconds
            self._recent_clicks = {k: v for k, v in self._recent_clicks.items() if v > cutoff}

        message = getattr(callback_query, "message", None)
        if not message:
            return False

        correlation_id = generate_correlation_id()

        # Parse callback data
        parts = callback_data.split(":")
        action = parts[0] if parts else ""

        logger.info(
            "callback_action_received",
            extra={"uid": uid, "action": action, "data": callback_data, "cid": correlation_id},
        )

        try:
            if action == "export":
                return await self._handle_export(message, uid, parts, correlation_id)
            if action == "translate":
                return await self._handle_translate(message, uid, parts, correlation_id)
            if action == "similar":
                return await self._handle_find_similar(message, uid, parts, correlation_id)
            if action == "save":
                return await self._handle_toggle_save(message, uid, parts, correlation_id)
            if action == "rate":
                return await self._handle_rate(message, uid, parts, correlation_id)
            if action == "multi_confirm_yes":
                return await self._handle_multi_confirm(message, uid, "yes", correlation_id)
            if action == "multi_confirm_no":
                return await self._handle_multi_confirm(message, uid, "no", correlation_id)

            logger.warning(
                "unknown_callback_action",
                extra={"action": action, "uid": uid, "cid": correlation_id},
            )
            return False

        except Exception as e:
            logger.exception(
                "callback_handler_error",
                extra={"action": action, "uid": uid, "error": str(e), "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(
                message,
                f"An error occurred. Error ID: {correlation_id}",
            )
            return True

    async def _handle_export(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle export callbacks (PDF, Markdown, HTML)."""
        if len(parts) < 3:
            logger.warning("export_missing_params", extra={"parts": parts, "cid": correlation_id})
            return False

        summary_id = parts[1]
        export_format = parts[2].lower()

        if export_format not in ("pdf", "md", "html"):
            await self.response_formatter.safe_reply(
                message, f"Unknown export format: {export_format}"
            )
            return True

        # Defer to export formatter (will be implemented)
        from app.adapters.external.formatting.export_formatter import ExportFormatter

        exporter = ExportFormatter(self.db)

        try:
            await self.response_formatter.safe_reply(
                message, f"Generating {export_format.upper()} export..."
            )

            file_path, filename = await exporter.export_summary(
                summary_id=summary_id,
                export_format=export_format,
                correlation_id=correlation_id,
            )

            if file_path and filename:
                await self._send_file(message, file_path, filename, export_format)
                logger.info(
                    "export_completed",
                    extra={
                        "format": export_format,
                        "summary_id": summary_id,
                        "cid": correlation_id,
                    },
                )
            else:
                await self.response_formatter.safe_reply(
                    message,
                    f"Export failed. Summary not found or export error. Error ID: {correlation_id}",
                )
        except Exception as e:
            logger.exception(
                "export_failed",
                extra={"format": export_format, "summary_id": summary_id, "error": str(e)},
            )
            await self.response_formatter.safe_reply(
                message,
                f"Export failed: {type(e).__name__}. Error ID: {correlation_id}",
            )

        return True

    async def _send_file(
        self, message: Any, file_path: str, filename: str, export_format: str
    ) -> None:
        """Send exported file as a document."""
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            await self.response_formatter.safe_reply(message, "Export file not found.")
            return

        caption_map = {
            "pdf": "PDF export",
            "md": "Markdown export",
            "html": "HTML export",
        }
        caption = caption_map.get(export_format, "Exported file")

        try:
            # Send as document
            if hasattr(message, "reply_document"):
                await message.reply_document(str(path), caption=caption)
            else:
                await self.response_formatter.safe_reply(
                    message, f"File ready: {filename} (unable to send as document)"
                )
        finally:
            # Clean up temp file
            try:
                path.unlink()
            except Exception:
                pass

    async def _handle_translate(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle translation request."""
        if len(parts) < 2:
            return False

        summary_id = parts[1]
        await self.response_formatter.safe_reply(
            message,
            "Translation feature coming soon. Use /help for available commands.",
        )
        logger.info(
            "translate_requested",
            extra={"summary_id": summary_id, "uid": uid, "cid": correlation_id},
        )
        return True

    async def _handle_find_similar(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle find similar summaries request."""
        if len(parts) < 2:
            return False

        summary_id = parts[1]
        await self.response_formatter.safe_reply(
            message,
            "Find similar feature coming soon. Use /search <query> to search your summaries.",
        )
        logger.info(
            "find_similar_requested",
            extra={"summary_id": summary_id, "uid": uid, "cid": correlation_id},
        )
        return True

    async def _handle_toggle_save(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle bookmark/favorite toggle."""
        if len(parts) < 2:
            return False

        summary_id = parts[1]

        try:
            from app.db.models import Summary

            # Find summary - support both Summary.id and Request.id (prefixed with 'req:')
            if summary_id.startswith("req:"):
                request_id = int(summary_id[4:])
                summary = Summary.get_or_none(Summary.request_id == request_id)
            else:
                summary = Summary.get_or_none(Summary.id == int(summary_id))

            if summary:
                summary.is_favorited = not summary.is_favorited
                summary.save()

                status = "saved to favorites" if summary.is_favorited else "removed from favorites"
                await self.response_formatter.safe_reply(message, f"Summary {status}.")
                logger.info(
                    "summary_favorite_toggled",
                    extra={
                        "summary_id": summary_id,
                        "is_favorited": summary.is_favorited,
                        "uid": uid,
                        "cid": correlation_id,
                    },
                )
            else:
                await self.response_formatter.safe_reply(message, "Summary not found.")
        except Exception as e:
            logger.exception(
                "toggle_save_failed",
                extra={"summary_id": summary_id, "error": str(e), "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(
                message, f"Failed to update favorite status. Error ID: {correlation_id}"
            )

        return True

    async def _handle_rate(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle summary rating (thumbs up/down)."""
        if len(parts) < 3:
            return False

        summary_id = parts[1]
        try:
            rating = int(parts[2])
        except ValueError:
            return False

        # For now, just acknowledge the rating
        # Future: Store in SummaryFeedback table
        rating_text = "positive" if rating > 0 else "negative"
        await self.response_formatter.safe_reply(
            message,
            f"Thanks for your {rating_text} feedback! This helps improve summarization quality.",
        )
        logger.info(
            "summary_rated",
            extra={
                "summary_id": summary_id,
                "rating": rating,
                "uid": uid,
                "cid": correlation_id,
            },
        )
        return True

    async def _handle_multi_confirm(
        self,
        message: Any,
        uid: int,
        response: str,
        correlation_id: str,
    ) -> bool:
        """Handle multi-link confirmation from button."""
        if not self.url_handler:
            logger.warning("multi_confirm_no_url_handler", extra={"cid": correlation_id})
            return False

        # This is handled by the existing flow in message_handler
        # Just log that we received it via callback
        logger.debug(
            "multi_confirm_callback",
            extra={"response": response, "uid": uid, "cid": correlation_id},
        )
        return False  # Let the existing handler process it
