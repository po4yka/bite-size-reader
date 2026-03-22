"""Action service for Telegram callback interactions."""

from __future__ import annotations

import asyncio
import html
import time
from typing import TYPE_CHECKING, Any, TypedDict, cast

from app.core.logging_utils import get_logger
from app.core.ui_strings import t

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.url_handler import URLHandler
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.search.hybrid_search_service import HybridSearchService

logger = get_logger(__name__)

# Timeout constants for expensive callback operations (seconds).
_CB_TIMEOUT_LLM = 120.0
_CB_TIMEOUT_SEARCH = 30.0
_CB_TIMEOUT_DIGEST = 180.0
_CB_TIMEOUT_EXPORT = 60.0

# Simple TTL cache for load_summary_payload() to avoid redundant DB queries
# when the same summary is accessed by multiple button clicks.
_SUMMARY_CACHE_TTL = 30.0
_SUMMARY_CACHE_MAX = 50


class _Insights(TypedDict, total=False):
    topic_overview: str
    new_facts: list[dict[str, Any]]


class CallbackActionService:
    """Executes callback actions while keeping transport orchestration thin."""

    def __init__(
        self,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        url_handler: URLHandler | None = None,
        hybrid_search: HybridSearchService | None = None,
        lang: str = "en",
    ) -> None:
        self.db = db
        self.response_formatter = response_formatter
        self.url_handler = url_handler
        self.hybrid_search = hybrid_search
        self._lang = lang
        self._summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def handle_digest_full_summary(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle digest full-summary callback (dg:channel_id:message_id)."""
        if len(parts) < 3:
            logger.warning("digest_callback_missing_params", extra={"parts": parts})
            return False

        try:
            channel_id = int(parts[1])
            msg_id = int(parts[2])
        except (ValueError, IndexError):
            logger.warning("digest_callback_invalid_params", extra={"parts": parts})
            await self.response_formatter.safe_reply(message, "Invalid digest callback data.")
            return True

        def _load_digest_post_sync(ch_id: int, m_id: int) -> Any:
            from app.db.models import Channel, ChannelPost

            return (
                ChannelPost.select()
                .join(Channel)
                .where(Channel.id == ch_id, ChannelPost.message_id == m_id)
                .first()
            )

        post = await asyncio.to_thread(_load_digest_post_sync, channel_id, msg_id)

        if not post:
            await self.response_formatter.safe_reply(message, "Post not found in database.")
            return True

        await self.response_formatter.safe_reply(message, t("cb_generating_summary", self._lang))

        post_url = post.url or ""
        if post_url and self.url_handler:
            try:
                await asyncio.wait_for(
                    self.url_handler.handle_single_url(
                        message=message,
                        url=post_url,
                        correlation_id=correlation_id,
                        interaction_id=0,
                    ),
                    timeout=_CB_TIMEOUT_DIGEST,
                )
            except TimeoutError:
                logger.warning(
                    "digest_full_summary_timeout",
                    extra={"cid": correlation_id, "timeout": _CB_TIMEOUT_DIGEST},
                )
                await self.response_formatter.safe_reply(message, t("cb_timeout", self._lang))
            except Exception as exc:
                logger.exception(
                    "digest_full_summary_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )
                await self._send_digest_post_fallback(message, post, post_url)
        else:
            await self._send_digest_post_fallback(message, post, post_url)

        logger.info(
            "digest_full_summary_sent",
            extra={
                "channel_id": channel_id,
                "message_id": msg_id,
                "uid": uid,
                "cid": correlation_id,
            },
        )
        return True

    async def _send_digest_post_fallback(self, message: Any, post: Any, post_url: str) -> None:
        text_preview = post.text[:4000]
        reply_text = f"**Full Post**\n\n{text_preview}"
        if post_url:
            reply_text += f"\n\n[Original]({post_url})"
        await self.response_formatter.safe_reply(message, reply_text)

    async def handle_export(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle export callbacks (PDF, Markdown, HTML)."""
        _ = uid
        if len(parts) < 3:
            logger.warning("export_missing_params", extra={"parts": parts, "cid": correlation_id})
            return False

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

        from app.adapters.external.formatting.export_formatter import ExportFormatter

        exporter = ExportFormatter(self.db)

        try:
            await self.response_formatter.safe_reply(
                message, t("cb_export_generating", self._lang).format(fmt=export_format.upper())
            )

            file_path, filename = await asyncio.wait_for(
                asyncio.to_thread(
                    exporter.export_summary,
                    summary_id=summary_id,
                    export_format=export_format,
                    correlation_id=correlation_id,
                ),
                timeout=_CB_TIMEOUT_EXPORT,
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
                    t("cb_export_failed", self._lang).format(cid=correlation_id),
                )
        except TimeoutError:
            logger.warning(
                "export_timeout",
                extra={"format": export_format, "summary_id": summary_id, "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(message, t("cb_timeout", self._lang))
        except Exception as exc:
            logger.exception(
                "export_failed",
                extra={"format": export_format, "summary_id": summary_id, "error": str(exc)},
            )
            await self.response_formatter.safe_reply(
                message,
                f"Export failed: {type(exc).__name__}. Error ID: {correlation_id}",
            )

        return True

    async def _send_file(
        self,
        message: Any,
        file_path: str,
        filename: str,
        export_format: str,
    ) -> None:
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
            if hasattr(message, "reply_document"):
                await message.reply_document(str(path), caption=caption)
            else:
                await self.response_formatter.safe_reply(
                    message,
                    f"File ready: {filename} (unable to send as document)",
                )
        finally:
            try:
                path.unlink()
            except Exception as exc:
                logger.debug("temp_file_cleanup_failed", extra={"error": str(exc)})

    async def handle_translate(
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
        summary_data = await self.load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, t("cb_summary_not_found", self._lang))
            return True

        if summary_data.get("lang") == "ru":
            await self.response_formatter.safe_reply(
                message, t("cb_translation_already_ru", self._lang)
            )
            return True

        if not self.url_handler:
            await self.response_formatter.send_error_notification(
                message,
                "unexpected_error",
                correlation_id,
                details="Translation service is temporarily unavailable.",
            )
            return True

        await self.response_formatter.safe_reply(
            message, t("cb_translation_processing", self._lang)
        )

        try:
            request_id = summary_data.get("request_id")
            if not isinstance(request_id, int):
                raise ValueError("Invalid request ID for translation")

            translated_text = await asyncio.wait_for(
                self.url_handler.translate_summary_to_ru(
                    summary=summary_data,
                    req_id=request_id,
                    correlation_id=correlation_id,
                    source_lang=summary_data.get("lang"),
                ),
                timeout=_CB_TIMEOUT_LLM,
            )

            if translated_text:
                await self.response_formatter.send_russian_translation(
                    message,
                    translated_text,
                    correlation_id=correlation_id,
                )
            else:
                await self.response_formatter.safe_reply(
                    message,
                    "Translation failed to generate meaningful output.",
                )
        except TimeoutError:
            logger.warning(
                "translation_timeout",
                extra={"summary_id": summary_id, "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(message, t("cb_timeout", self._lang))
        except Exception as exc:
            logger.exception(
                "translation_failed",
                extra={"summary_id": summary_id, "error": str(exc), "cid": correlation_id},
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

    async def handle_find_similar(
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
        summary_data = await self.load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, t("cb_summary_not_found", self._lang))
            return True

        if not self.hybrid_search:
            await self.response_formatter.safe_reply(
                message,
                t("cb_search_unavailable", self._lang),
            )
            return True

        meta = summary_data.get("metadata") or {}
        title = str(meta.get("title") or "")
        key_ideas = summary_data.get("key_ideas") or []
        tags = summary_data.get("topic_tags") or []

        query_parts: list[str] = []
        if title:
            query_parts.append(title)

        if tags and isinstance(tags, list):
            query_parts.extend([str(tag) for tag in tags[:2] if str(tag).strip()])

        if not query_parts and key_ideas and isinstance(key_ideas, list):
            first_idea = str(key_ideas[0]) if key_ideas else ""
            if first_idea:
                query_parts.append(first_idea[:100])

        query = " ".join(query_parts).strip()
        if not query:
            await self.response_formatter.safe_reply(message, t("cb_not_enough_info", self._lang))
            return True

        await self.response_formatter.safe_reply(
            message,
            f"🔍 {t('cb_finding_similar', self._lang).format(title=html.escape(title or 'this item'))}",
            parse_mode="HTML",
        )

        try:
            results = await asyncio.wait_for(
                self.hybrid_search.search(query, correlation_id=correlation_id),
                timeout=_CB_TIMEOUT_SEARCH,
            )

            current_url = summary_data.get("url")
            filtered_results = [
                result for result in results if not (current_url and result.url == current_url)
            ]

            if not filtered_results:
                await self.response_formatter.safe_reply(message, t("cb_no_similar", self._lang))
            else:
                await self.response_formatter.send_topic_search_results(
                    message,
                    topic=f"Similar to: {title[:30]}...",
                    articles=filtered_results,
                    source="hybrid",
                )
        except TimeoutError:
            logger.warning(
                "find_similar_timeout",
                extra={"summary_id": summary_id, "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(message, t("cb_timeout", self._lang))
        except Exception as exc:
            logger.exception(
                "find_similar_failed",
                extra={"summary_id": summary_id, "error": str(exc), "cid": correlation_id},
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

    async def handle_toggle_save(
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

            def _toggle_save_sync(sid: str) -> bool | None:
                """Toggle favorite in a thread. Returns new state or None."""
                from app.db.models import Summary

                if sid.startswith("req:"):
                    req_id = int(sid[4:])
                    summary = Summary.get_or_none(Summary.request_id == req_id)
                else:
                    summary = Summary.get_or_none(Summary.id == int(sid))
                if not summary:
                    return None
                summary.is_favorited = not summary.is_favorited
                summary.save()
                return summary.is_favorited

            new_state = await asyncio.to_thread(_toggle_save_sync, summary_id)

            # Invalidate cache after write.
            self._summary_cache.pop(summary_id, None)

            if new_state is not None:
                status_msg = t("cb_saved", self._lang) if new_state else t("cb_removed", self._lang)
                await self.response_formatter.safe_reply(message, status_msg)
                logger.info(
                    "summary_favorite_toggled",
                    extra={
                        "summary_id": summary_id,
                        "is_favorited": new_state,
                        "uid": uid,
                        "cid": correlation_id,
                    },
                )
            else:
                await self.response_formatter.safe_reply(
                    message, t("cb_summary_not_found", self._lang)
                )
        except Exception as exc:
            logger.exception(
                "toggle_save_failed",
                extra={"summary_id": summary_id, "error": str(exc), "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(
                message,
                f"Failed to update favorite status. Error ID: {correlation_id}",
            )

        return True

    async def handle_rate(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle summary rating (thumbs up/down)."""
        if len(parts) < 3:
            return False

        summary_id = ":".join(parts[1:-1]).strip()
        if not summary_id:
            return False

        try:
            rating = int(parts[-1])
        except ValueError:
            return False

        rating_text = (
            t("cb_feedback_positive", self._lang)
            if rating > 0
            else t("cb_feedback_negative", self._lang)
        )
        await self.response_formatter.safe_reply(
            message,
            t("cb_feedback_thanks", self._lang).format(rating=rating_text),
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

    async def handle_more(
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
        summary_data = await self.load_summary_payload(summary_id, correlation_id=correlation_id)
        if not summary_data:
            await self.response_formatter.safe_reply(message, t("cb_summary_not_found", self._lang))
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

        raw_insights = summary_data.get("insights") or {}
        insights: _Insights = (
            cast("_Insights", raw_insights) if isinstance(raw_insights, dict) else {}
        )

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
            lines.extend(
                ["", f"<b>{t('more_long_summary', self._lang)}</b>", html.escape(summary_1000)]
            )

        overview = str(insights.get("topic_overview") or "").strip()
        new_facts = insights.get("new_facts") or []
        if overview or (isinstance(new_facts, list) and new_facts):
            lines.extend(["", f"<b>{t('more_research_highlights', self._lang)}</b>"])
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
            lines.extend(["", f"<b>{t('more_answered_questions', self._lang)}</b>"])
            for question in answered[:5]:
                question_text = str(question).strip()
                if question_text:
                    lines.append("• " + html.escape(question_text))

        if tags:
            clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
            if clean_tags:
                shown = clean_tags[:5]
                hidden = max(0, len(clean_tags) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.extend(
                    [
                        "",
                        f"<b>{t('more_tags', self._lang)}</b>",
                        html.escape(" ".join(shown) + tail),
                    ]
                )

        if people or orgs or locs:
            lines.extend(["", f"<b>{t('more_entities', self._lang)}</b>"])
            if people:
                shown = people[:5]
                hidden = max(0, len(people) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append(
                    f"• {t('people', self._lang)}: " + html.escape(", ".join(shown) + tail)
                )
            if orgs:
                shown = orgs[:5]
                hidden = max(0, len(orgs) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append(f"• {t('orgs', self._lang)}: " + html.escape(", ".join(shown) + tail))
            if locs:
                shown = locs[:5]
                hidden = max(0, len(locs) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                lines.append(
                    f"• {t('places', self._lang)}: " + html.escape(", ".join(shown) + tail)
                )

        text = "\n".join(lines).strip() or t("cb_no_details", self._lang)
        await self.response_formatter.safe_reply(message, text, parse_mode="HTML")
        logger.info(
            "more_details_sent",
            extra={"summary_id": summary_id, "uid": uid, "cid": correlation_id},
        )
        return True

    async def handle_show_related_summary(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Handle a click on a related-read button (rel:<request_id>)."""
        _ = uid
        if len(parts) < 2:
            return False

        try:
            request_id = int(parts[1])
        except (ValueError, IndexError):
            return False

        summary_data = await self.load_summary_payload(
            f"req:{request_id}", correlation_id=correlation_id
        )
        if not summary_data:
            await self.response_formatter.safe_reply(message, t("cb_related_not_found", self._lang))
            return True

        title = summary_data.get("title") or ""
        tldr = summary_data.get("tldr") or ""
        key_ideas: list[str] = summary_data.get("key_ideas") or []
        tags: list[str] = summary_data.get("topic_tags") or []
        url = summary_data.get("url") or ""

        lines: list[str] = []
        if title:
            lines.append(f"<b>{html.escape(title)}</b>")
        if tldr:
            lines.append(f"\n{html.escape(tldr)}")
        if key_ideas:
            lines.append("")
            for idea in key_ideas[:3]:
                lines.append(f"  - {html.escape(str(idea))}")
        if tags:
            lines.append(f"\n{html.escape(', '.join(str(t_) for t_ in tags[:6]))}")
        if url:
            lines.append(f'\n<a href="{html.escape(url)}">Source</a>')

        text = "\n".join(lines).strip()
        if not text:
            text = t("cb_no_details", self._lang)

        from app.adapters.external.formatting.summary.action_buttons import (
            create_inline_keyboard,
        )

        summary_id = summary_data.get("id", "")
        keyboard = create_inline_keyboard(
            summary_id, correlation_id=correlation_id, lang=self._lang
        )
        await self.response_formatter.safe_reply(
            message, text, parse_mode="HTML", reply_markup=keyboard
        )
        return True

    async def load_summary_payload(
        self,
        summary_id: str,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Load summary JSON payload from database (supports 'req:' IDs).

        Uses a short-lived TTL cache to avoid redundant DB queries when the
        same summary is accessed by multiple button clicks in quick succession.
        """
        now = time.time()
        cached = self._summary_cache.get(summary_id)
        if cached is not None:
            cached_at, cached_payload = cached
            if now - cached_at < _SUMMARY_CACHE_TTL:
                return cached_payload

        try:
            result = await asyncio.to_thread(self._load_summary_payload_sync, summary_id)
            if result is not None:
                # Evict oldest entries if cache is full.
                if len(self._summary_cache) >= _SUMMARY_CACHE_MAX:
                    oldest_key = min(self._summary_cache, key=lambda k: self._summary_cache[k][0])
                    self._summary_cache.pop(oldest_key, None)
                self._summary_cache[summary_id] = (now, result)
            return result
        except Exception as exc:
            logger.exception(
                "load_summary_payload_failed",
                extra={"summary_id": summary_id, "error": str(exc), "cid": correlation_id},
            )
            return None

    @staticmethod
    def _load_summary_payload_sync(summary_id: str) -> dict[str, Any] | None:
        """Synchronous DB lookup -- run via asyncio.to_thread()."""
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
            "insights": summary.insights_json if isinstance(summary.insights_json, dict) else None,
            **payload,
        }

    async def handle_retry(
        self,
        message: Any,
        uid: int,
        parts: list[str],
        correlation_id: str,
    ) -> bool:
        """Retry a failed URL summarization (retry:<original_correlation_id>)."""
        if len(parts) < 2:
            logger.warning("retry_callback_missing_cid", extra={"parts": parts})
            return False

        original_cid = parts[1]

        def _lookup_url(cid: str) -> str | None:
            from app.db.models import Request

            req = (
                Request.select(Request.input_url)
                .where(Request.correlation_id == cid)
                .order_by(Request.created_at.desc())
                .first()
            )
            return req.input_url if req else None

        url = await asyncio.to_thread(_lookup_url, original_cid)
        if not url:
            logger.warning(
                "retry_url_not_found",
                extra={"original_cid": original_cid, "uid": uid, "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(
                message, t("cb_retry_url_not_found", self._lang)
            )
            return True

        if not self.url_handler:
            logger.error("retry_no_url_handler", extra={"cid": correlation_id})
            await self.response_formatter.safe_reply(message, t("cb_retry_unavailable", self._lang))
            return True

        await self.response_formatter.safe_reply(message, t("cb_retrying", self._lang))

        try:
            await asyncio.wait_for(
                self.url_handler.handle_single_url(
                    message=message,
                    url=url,
                    correlation_id=correlation_id,
                ),
                timeout=_CB_TIMEOUT_LLM,
            )
        except TimeoutError:
            logger.warning(
                "retry_timeout",
                extra={"cid": correlation_id, "url": url, "timeout": _CB_TIMEOUT_LLM},
            )
            await self.response_formatter.safe_reply(message, t("cb_timeout", self._lang))
        except Exception as exc:
            logger.exception(
                "retry_failed",
                extra={"cid": correlation_id, "url": url, "error": str(exc)},
            )
            await self.response_formatter.send_error_notification(
                message, "processing_failed", correlation_id
            )

        return True
