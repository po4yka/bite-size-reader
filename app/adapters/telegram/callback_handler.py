"""Callback handler for inline button interactions."""

from __future__ import annotations

import html
import logging
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import generate_correlation_id

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager
    from app.services.hybrid_search_service import HybridSearchService

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
#   "more:abc123"           - Show additional details


class CallbackHandler:
    """Handles inline button callback queries for post-summary actions."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_handler: URLHandler | None = None,
        hybrid_search: HybridSearchService | None = None,
    ) -> None:
        self.db = db
        self.response_formatter = response_formatter
        self.url_handler = url_handler
        self.hybrid_search = hybrid_search
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
            if action == "more":
                return await self._handle_more(message, uid, parts, correlation_id)

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
            await self.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="The button action could not be completed.",
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

        # summary_id may itself contain ":" (e.g. "req:123"), so treat the last part as the format
        summary_id = ":".join(parts[1:-1]).strip()
        export_format = parts[-1].lower()
        if not summary_id:
            logger.warning(
                "export_missing_summary_id", extra={"parts": parts, "cid": correlation_id}
            )
            return False

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
                logger.debug("temp_file_cleanup_failed", exc_info=True)

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

        summary_id = ":".join(parts[1:]).strip()
        summary_data = await self._load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, "Summary not found.")
            return True

        if summary_data.get("lang") == "ru":
            await self.response_formatter.safe_reply(message, "This summary is already in Russian.")
            return True

        if not self.url_handler or not hasattr(self.url_handler, "url_processor"):
            await self.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="Translation service is temporarily unavailable.",
            )
            return True

        await self.response_formatter.safe_reply(
            message, "Translation feature request received. Processing..."
        )

        try:
            # We need the request_id to perform translation
            request_id = summary_data.get("request_id")
            if not isinstance(request_id, int):
                raise ValueError("Invalid request ID for translation")

            # Call translation service via URL processor
            translated_text = await self.url_handler.url_processor.translate_summary_to_ru(
                summary=summary_data,
                req_id=request_id,
                correlation_id=correlation_id,
                source_lang=summary_data.get("lang"),
            )

            if translated_text:
                await self.response_formatter.send_russian_translation(
                    message, translated_text, correlation_id=correlation_id
                )
            else:
                await self.response_formatter.safe_reply(
                    message, "Translation failed to generate meaningful output."
                )

        except Exception as e:
            logger.exception(
                "translation_failed",
                extra={"summary_id": summary_id, "error": str(e), "cid": correlation_id},
            )
            await self.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="An error occurred during translation.",
            )

        logger.info(
            "translate_completed",
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

        summary_id = ":".join(parts[1:]).strip()
        summary_data = await self._load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, "Summary not found.")
            return True

        if not self.hybrid_search:
            await self.response_formatter.safe_reply(
                message,
                "Search service is currently unavailable.",
            )
            return True

        # Construct query from summary metadata
        meta = summary_data.get("metadata") or {}
        title = str(meta.get("title") or "")

        # Also try key ideas or tags
        key_ideas = summary_data.get("key_ideas") or []
        tags = summary_data.get("topic_tags") or []

        query_parts = []
        if title:
            query_parts.append(title)

        # Add top 2 tags if available
        if tags and isinstance(tags, list):
            query_parts.extend([str(t) for t in tags[:2] if str(t).strip()])

        if not query_parts and key_ideas and isinstance(key_ideas, list):
            # Fallback to first key idea if no title/tags
            first_idea = str(key_ideas[0]) if key_ideas else ""
            if first_idea:
                query_parts.append(first_idea[:100])

        query = " ".join(query_parts).strip()
        if not query:
            await self.response_formatter.safe_reply(
                message, "Not enough information to perform similarity search."
            )
            return True

        await self.response_formatter.safe_reply(
            message,
            f"🔍 Finding similar summaries for: <b>{html.escape(title or 'this item')}</b>...",
            parse_mode="HTML",
        )

        try:
            # Exclude current item from results if possible (not supported by search API yet,
            # but we can filter manually if needed, though usually semantic search handles it)
            results = await self.hybrid_search.search(query, correlation_id=correlation_id)

            # Filter out the current summary if it appears in results
            current_url = summary_data.get("url")
            filtered_results = []
            for r in results:
                # Basic check to avoid showing the exact same item
                if current_url and r.url == current_url:
                    continue
                filtered_results.append(r)

            if not filtered_results:
                await self.response_formatter.safe_reply(message, "No similar summaries found.")
            else:
                await self.response_formatter.send_topic_search_results(
                    message,
                    topic=f"Similar to: {title[:30]}...",
                    articles=filtered_results,
                    source="hybrid",
                )

        except Exception as e:
            logger.exception(
                "find_similar_failed",
                extra={"summary_id": summary_id, "error": str(e), "cid": correlation_id},
            )
            await self.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="An error occurred while searching for similar content.",
            )

        logger.info(
            "find_similar_completed",
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

        summary_id = ":".join(parts[1:]).strip()

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

        # summary_id may contain ":" (e.g. "req:123"), so treat the last part as rating
        summary_id = ":".join(parts[1:-1]).strip()
        if not summary_id:
            return False
        try:
            rating = int(parts[-1])
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

    async def _handle_more(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Show additional details for a summary without spamming the default card."""
        if len(parts) < 2:
            return False

        summary_id = ":".join(parts[1:]).strip()
        summary_data = await self._load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, "Summary not found.")
            return True

        meta = summary_data.get("metadata") or {}
        title = ""
        domain = ""
        if isinstance(meta, dict):
            title = str(meta.get("title") or "").strip()
            domain = str(meta.get("domain") or "").strip()

        summary_1000 = str(summary_data.get("summary_1000") or "").strip()
        if not summary_1000:
            summary_1000 = str(summary_data.get("tldr") or "").strip()

        insights = summary_data.get("insights") or {}
        if not isinstance(insights, dict):
            insights = {}

        tags = summary_data.get("topic_tags") or []
        if not isinstance(tags, list):
            tags = []

        entities = summary_data.get("entities") or {}
        people: list[str] = []
        orgs: list[str] = []
        locs: list[str] = []
        if isinstance(entities, dict):
            people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
            orgs = [str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()]
            locs = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]

        answered = summary_data.get("answered_questions") or []
        if not isinstance(answered, list):
            answered = []

        lines: list[str] = []
        if title:
            lines.append(f"<b>{html.escape(title)}</b>")
        if domain:
            lines.append(f"<i>{html.escape(domain)}</i>")

        if summary_1000:
            lines.extend(["", "<b>Long summary</b>", html.escape(summary_1000)])

        overview = str(insights.get("topic_overview") or "").strip()
        new_facts = insights.get("new_facts") or []
        if overview or (isinstance(new_facts, list) and new_facts):
            lines.extend(["", "<b>Research highlights</b>"])
            if overview:
                overview_short = overview if len(overview) <= 500 else overview[:497].rstrip() + "…"
                lines.append(html.escape(overview_short))
            if isinstance(new_facts, list):
                for item in new_facts[:3]:
                    if isinstance(item, dict):
                        fact = str(item.get("fact") or "").strip()
                    else:
                        fact = str(item).strip()
                    if not fact:
                        continue
                    fact_short = fact if len(fact) <= 220 else fact[:217].rstrip() + "…"
                    lines.append("• " + html.escape(fact_short))

        if answered:
            lines.extend(["", "<b>Answered questions</b>"])
            for q in answered[:5]:
                q_s = str(q).strip()
                if q_s:
                    lines.append("• " + html.escape(q_s))

        if tags:
            clean_tags = [str(t).strip() for t in tags if str(t).strip()]
            if clean_tags:
                shown = clean_tags[:5]
                hidden = max(0, len(clean_tags) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.extend(["", "<b>Tags</b>", html.escape(" ".join(shown) + tail)])

        if people or orgs or locs:
            lines.append("")
            lines.append("<b>Entities</b>")
            if people:
                shown = people[:5]
                hidden = max(0, len(people) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append("• People: " + html.escape(", ".join(shown) + tail))
            if orgs:
                shown = orgs[:5]
                hidden = max(0, len(orgs) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append("• Orgs: " + html.escape(", ".join(shown) + tail))
            if locs:
                shown = locs[:5]
                hidden = max(0, len(locs) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append("• Places: " + html.escape(", ".join(shown) + tail))

        text = "\n".join(lines).strip() or "No additional details available."
        await self.response_formatter.safe_reply(message, text, parse_mode="HTML")
        logger.info(
            "more_details_sent",
            extra={"summary_id": summary_id, "uid": uid, "cid": correlation_id},
        )
        return True

    async def _load_summary_payload(
        self, summary_id: str, *, correlation_id: str | None = None
    ) -> dict[str, Any] | None:
        """Load summary JSON payload from database (supports 'req:' IDs)."""
        try:
            from app.db.models import Request, Summary

            if summary_id.startswith("req:"):
                request_id = int(summary_id[4:])
                summary = Summary.get_or_none(Summary.request_id == request_id)
            else:
                summary = Summary.get_or_none(Summary.id == int(summary_id))

            if not summary:
                return None

            request = Request.get_or_none(Request.id == summary.request_id)
            url = request.normalized_url if request else None

            payload = summary.json_payload or {}
            if not isinstance(payload, dict):
                payload = {}

            return {
                "id": str(summary.id),
                "request_id": summary.request_id,
                "url": url,
                "lang": summary.lang,
                "insights": summary.insights_json
                if isinstance(summary.insights_json, dict)
                else None,
                **payload,
            }
        except Exception as e:
            logger.exception(
                "load_summary_payload_failed",
                extra={"summary_id": summary_id, "error": str(e), "cid": correlation_id},
            )
            return None
