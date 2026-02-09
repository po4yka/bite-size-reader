"""Summary presentation formatting."""

from __future__ import annotations

import html
import logging
import re
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from app.adapters.external.formatting.data_formatter import DataFormatterImpl
    from app.adapters.external.formatting.response_sender import ResponseSenderImpl
    from app.adapters.external.formatting.text_processor import TextProcessorImpl
    from app.core.progress_tracker import ProgressTracker
    from app.core.verbosity import VerbosityResolver

logger = logging.getLogger(__name__)


class SummaryPresenterImpl:
    """Implementation of summary presentation."""

    @staticmethod
    def _truncate_plain_text(text: str, max_len: int) -> str:
        from app.adapters.external.formatting.summary_presenter_parts.card import (
            truncate_plain_text,
        )

        return truncate_plain_text(text, max_len)

    @staticmethod
    def _extract_domain_from_url(url: str) -> str | None:
        from app.adapters.external.formatting.summary_presenter_parts.card import (
            extract_domain_from_url,
        )

        return extract_domain_from_url(url)

    def _compact_tldr(self, text: str, *, max_sentences: int = 3, max_chars: int = 520) -> str:
        """Return the first 2-3 sentences (best-effort) for the card TL;DR."""
        from app.adapters.external.formatting.summary_presenter_parts.card import compact_tldr

        return compact_tldr(
            text,
            text_processor=self._text_processor,
            max_sentences=max_sentences,
            max_chars=max_chars,
        )

    def _build_compact_card_html(
        self, summary_shaped: dict[str, Any], llm: Any, chunks: int | None, *, reader: bool
    ) -> str:
        """Build a compact, scannable summary card in Telegram HTML format."""
        from app.adapters.external.formatting.summary_presenter_parts.card import (
            build_compact_card_html,
        )

        return build_compact_card_html(
            summary_shaped,
            llm,
            chunks,
            reader=reader,
            text_processor=self._text_processor,
            data_formatter=self._data_formatter,
        )

    def __init__(
        self,
        response_sender: ResponseSenderImpl,
        text_processor: TextProcessorImpl,
        data_formatter: DataFormatterImpl,
        *,
        verbosity_resolver: VerbosityResolver | None = None,
        progress_tracker: ProgressTracker | None = None,
    ) -> None:
        """Initialize the summary presenter.

        Args:
            response_sender: Response sender for sending messages.
            text_processor: Text processor for text operations.
            data_formatter: Data formatter for formatting values.
            verbosity_resolver: Optional resolver for per-user verbosity.
            progress_tracker: Optional tracker to clear when summary is ready.
        """
        self._response_sender = response_sender
        self._text_processor = text_processor
        self._data_formatter = data_formatter
        self._verbosity_resolver = verbosity_resolver
        self._progress_tracker = progress_tracker

    def _create_action_buttons(self, summary_id: int | str) -> list[list[dict[str, str]]]:
        """Create inline keyboard buttons for post-summary actions.

        Returns a 2D list of button rows for InlineKeyboardMarkup.
        """
        from app.adapters.external.formatting.summary_presenter_parts.actions import (
            create_action_buttons,
        )

        return create_action_buttons(summary_id)

    def _create_inline_keyboard(
        self, summary_id: int | str, correlation_id: str | None = None
    ) -> Any:
        """Create an inline keyboard markup for post-summary actions."""
        from app.adapters.external.formatting.summary_presenter_parts.actions import (
            create_inline_keyboard,
        )

        return create_inline_keyboard(summary_id, correlation_id)

    async def _send_action_buttons(
        self, message: Any, summary_id: int | str, correlation_id: str | None = None
    ) -> None:
        """Send action buttons as a separate message after the summary."""
        try:
            keyboard = self._create_inline_keyboard(summary_id, correlation_id)
            if keyboard:
                await self._response_sender.safe_reply(
                    message,
                    "Quick Actions:",
                    reply_markup=keyboard,
                )
                logger.debug(
                    "action_buttons_sent",
                    extra={"summary_id": summary_id},
                )
        except Exception as e:
            raise_if_cancelled(e)
            logger.warning(
                "send_action_buttons_failed",
                extra={"summary_id": summary_id, "error": str(e)},
            )

    async def send_structured_summary_response(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None = None,
        summary_id: int | str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Send summary where each top-level JSON field is a separate message,
        then attach the full JSON as a .json document with a descriptive filename.

        Args:
            message: Telegram message object
            summary_shaped: Summary data dictionary
            llm: LLM instance (for model name)
            chunks: Number of chunks used (optional)
            summary_id: Database summary ID for action buttons (optional)
            correlation_id: Request correlation ID for tracing (optional)
        """
        try:
            # Determine verbosity once (default: DEBUG when resolver isn't available)
            reader = False
            if self._verbosity_resolver is not None:
                from app.core.verbosity import VerbosityLevel

                reader = (
                    await self._verbosity_resolver.get_verbosity(message)
                ) == VerbosityLevel.READER

            # In Reader mode (and when a ProgressTracker is available), edit the existing
            # consolidated "job card" message into the final summary instead of sending
            # multiple messages.
            job_card_finalized = False

            try:
                card_text = self._build_compact_card_html(
                    summary_shaped,
                    llm,
                    chunks,
                    reader=reader,
                )

                if self._progress_tracker is not None:
                    keyboard = self._create_inline_keyboard(summary_id) if summary_id else None
                    result = await self._progress_tracker.finalize(
                        message,
                        card_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    if result is not None:
                        job_card_finalized = True
                        if reader:
                            return
                    else:
                        logger.warning(
                            "progress_finalize_failed_fallback",
                            extra={"request_message_id": getattr(message, "id", None)},
                        )
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.warning(
                    "compact_card_build_failed",
                    extra={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                        "request_message_id": getattr(message, "id", None),
                    },
                )

            # Optional short header (only when we didn't finalize into a job card)
            if not reader and not job_card_finalized:
                try:
                    method = f"Chunked ({chunks} parts)" if chunks else "Single-pass"
                    model_name = getattr(llm, "model", None)
                    header = f"Summary Ready\nModel: {model_name or 'unknown'}\nMethod: {method}"
                    await self._response_sender.safe_reply(message, header)
                except Exception as exc:
                    raise_if_cancelled(exc)

            # Combined first message: TL;DR, Tags, Entities, Reading Time, Key Stats, Readability
            combined_lines: list[str] = []

            tl_dr = str(summary_shaped.get("summary_250", "")).strip()
            if tl_dr:
                tl_dr_clean = self._text_processor.sanitize_summary_text(tl_dr)
                combined_lines.extend(["📋 TL;DR:", tl_dr_clean, ""])

            tags = [
                str(t).strip() for t in (summary_shaped.get("topic_tags") or []) if str(t).strip()
            ]
            if tags:
                shown = tags[:5]
                hidden = max(0, len(tags) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                combined_lines.append("🏷️ Tags: " + " ".join(shown) + tail)
                combined_lines.append("")

            entities = summary_shaped.get("entities") or {}
            if isinstance(entities, dict):
                people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
                orgs = [
                    str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()
                ]
                locs = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]
                if people or orgs or locs:
                    combined_lines.append("🧭 Entities:")
                    if people:
                        shown = people[:5]
                        hidden = max(0, len(people) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• People: " + ", ".join(shown) + tail)
                    if orgs:
                        shown = orgs[:5]
                        hidden = max(0, len(orgs) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• Orgs: " + ", ".join(shown) + tail)
                    if locs:
                        shown = locs[:5]
                        hidden = max(0, len(locs) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• Places: " + ", ".join(shown) + tail)
                    combined_lines.append("")

            reading_time = summary_shaped.get("estimated_reading_time_min")
            if reading_time:
                combined_lines.append(f"⏱️ Reading time: ~{reading_time} min")
                combined_lines.append("")

            key_stats = summary_shaped.get("key_stats") or []
            if isinstance(key_stats, list) and key_stats:
                ks_lines = self._data_formatter.format_key_stats(key_stats[:10])
                if ks_lines:
                    combined_lines.append("📈 Key Stats:")
                    combined_lines.extend(ks_lines)
                    combined_lines.append("")

            readability = summary_shaped.get("readability") or {}
            readability_line = self._data_formatter.format_readability(readability)
            if readability_line:
                combined_lines.append(f"🧮 Readability — {readability_line}")
                combined_lines.append("")

            metadata = summary_shaped.get("metadata") or {}
            if isinstance(metadata, dict):
                meta_parts = []
                if metadata.get("title"):
                    meta_parts.append(f"📰 {metadata['title']}")
                if metadata.get("author"):
                    meta_parts.append(f"✍️ {metadata['author']}")
                if metadata.get("domain"):
                    meta_parts.append(f"🌐 {metadata['domain']}")
                if meta_parts:
                    combined_lines.extend(meta_parts)
                    combined_lines.append("")

            # Categories & Topic Taxonomy
            categories = [
                str(c).strip() for c in (summary_shaped.get("categories") or []) if str(c).strip()
            ]
            if categories:
                combined_lines.append("📁 Categories: " + ", ".join(categories[:10]))
                combined_lines.append("")

            # Confidence & Risk
            confidence = summary_shaped.get("confidence", 1.0)
            risk = summary_shaped.get("hallucination_risk", "low")
            if isinstance(confidence, int | float) and confidence < 1.0:
                combined_lines.append(f"🎯 Confidence: {confidence:.1%}")
            if risk != "low":
                risk_emoji = "⚠️" if risk == "med" else "🚨"
                combined_lines.append(f"{risk_emoji} Hallucination risk: {risk}")
            if confidence < 1.0 or risk != "low":
                combined_lines.append("")

            if combined_lines and not job_card_finalized:
                # Remove trailing empty lines
                while combined_lines and not combined_lines[-1]:
                    combined_lines.pop()
                await self._text_processor.send_long_text(message, "\n".join(combined_lines))

            # Send separated summary fields (summary_250, summary_500, tldr, ...)
            summary_fields = [
                k
                for k in summary_shaped
                if ((k.startswith("summary_") and k.split("_", 1)[1].isdigit()) or k == "tldr")
            ]
            if job_card_finalized:
                # The card already shows tldr; skip it in the expanded fields
                summary_fields = [k for k in summary_fields if k != "tldr"]

            def _key_num(k: str) -> int:
                if k == "tldr":
                    return 10_000
                try:
                    return int(k.split("_", 1)[1])
                except Exception:
                    logger.debug("sort_key_extraction_failed", exc_info=True)
                    return 0

            for key in sorted(summary_fields, key=_key_num):
                content = str(summary_shaped.get(key, "")).strip()
                if content:
                    content = self._text_processor.sanitize_summary_text(content)
                    if key == "tldr":
                        label = "🧾 TL;DR"
                    else:
                        label = f"🧾 Summary {key.split('_', 1)[1]}"
                    await self._text_processor.send_labelled_text(
                        message,
                        label,
                        content,
                    )

            # Key ideas as separate messages
            ideas = [
                str(x).strip() for x in (summary_shaped.get("key_ideas") or []) if str(x).strip()
            ]
            if ideas:
                chunk: list[str] = []
                for idea in ideas:
                    chunk.append(f"• {idea}")
                    if sum(len(c) + 1 for c in chunk) > 3000:
                        await self._text_processor.send_long_text(
                            message,
                            "<b>💡 Key Ideas</b>\n" + "\n".join(chunk),
                            parse_mode="HTML",
                        )
                        chunk = []
                if chunk:
                    await self._text_processor.send_long_text(
                        message,
                        "<b>💡 Key Ideas</b>\n" + "\n".join(chunk),
                        parse_mode="HTML",
                    )

            # Send new field messages
            await self._send_new_field_messages(message, summary_shaped)

            # Finally attach full JSON as a document with a descriptive filename
            await self._response_sender.reply_json(message, summary_shaped)

            # Add action buttons after summary if summary_id is available
            if summary_id and not job_card_finalized:
                await self._send_action_buttons(message, summary_id, correlation_id)

        except Exception as exc:
            raise_if_cancelled(exc)
            # Fallback to simpler format
            try:
                tl_dr = str(summary_shaped.get("summary_250", "")).strip()
                if tl_dr:
                    await self._response_sender.safe_reply(message, f"📋 TL;DR:\n{tl_dr}")
            except Exception as exc2:
                raise_if_cancelled(exc2)

            await self._response_sender.reply_json(message, summary_shaped)

            # Still try to add action buttons in fallback
            if summary_id:
                await self._send_action_buttons(message, summary_id, correlation_id)

    async def send_russian_translation(
        self, message: Any, translated_text: str, correlation_id: str | None = None
    ) -> None:
        """Send the adapted Russian translation as a follow-up message."""
        if not translated_text or not translated_text.strip():
            logger.warning("russian_translation_empty", extra={"cid": correlation_id})
            return

        cleaned = self._text_processor.sanitize_summary_text(translated_text.strip())
        header = "\u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u0440\u0435\u0437\u044e\u043c\u0435"

        reader = False
        if self._verbosity_resolver is not None:
            from app.core.verbosity import VerbosityLevel

            reader = (
                await self._verbosity_resolver.get_verbosity(message)
            ) == VerbosityLevel.READER

        if correlation_id and not reader:
            header += f"\nCorrelation ID: {correlation_id}"

        await self._response_sender.safe_reply(message, header)
        await self._text_processor.send_long_text(message, cleaned)

    async def send_additional_insights_message(
        self, message: Any, insights: dict[str, Any], correlation_id: str | None = None
    ) -> None:
        """Send follow-up message summarizing additional research insights."""
        try:
            import html

            # Skip sending in Reader mode (the calling code should already gate on this),
            # but keep the check here for safety when called directly.
            if self._verbosity_resolver is not None:
                from app.core.verbosity import VerbosityLevel

                if (await self._verbosity_resolver.get_verbosity(message)) == VerbosityLevel.READER:
                    return

            def _cap(text: str, max_chars: int) -> str:
                cleaned = self._text_processor.sanitize_summary_text(text.strip())
                if len(cleaned) <= max_chars:
                    return cleaned
                return cleaned[: max(0, max_chars - 1)].rstrip() + "…"

            def _safe_html(text: str, *, max_chars: int = 900) -> str:
                cleaned = _cap(text, max_chars)
                escaped = html.escape(cleaned)
                return self._text_processor.linkify_urls(escaped)

            def _clean_list(
                items: list[Any], *, limit: int, item_max_chars: int = 220
            ) -> list[str]:
                cleaned: list[str] = []
                for item in items:
                    text = str(item).strip()
                    if not text:
                        continue
                    cleaned.append(_safe_html(text, max_chars=item_max_chars))
                    if len(cleaned) >= limit:
                        break
                return cleaned

            lines: list[str] = ["<b>🔎 Additional Research Highlights</b>"]
            if correlation_id:
                lines.append(
                    f"<i>Correlation ID:</i> <code>{html.escape(str(correlation_id))}</code>"
                )

            sections_sent = False

            overview = insights.get("topic_overview")
            if isinstance(overview, str) and overview.strip():
                sections_sent = True
                lines.extend(["", "<b>🧭 Overview</b>", _safe_html(overview, max_chars=1200)])

            facts_section: list[str] = []
            facts = insights.get("new_facts")
            if isinstance(facts, list):
                for idx, fact in enumerate(facts[:5], start=1):
                    if not isinstance(fact, dict):
                        continue
                    fact_text = str(fact.get("fact", "")).strip()
                    if not fact_text:
                        continue
                    fact_lines = [f"<b>{idx}.</b> {_safe_html(fact_text, max_chars=320)}"]

                    why_matters = str(fact.get("why_it_matters", "")).strip()
                    if why_matters:
                        fact_lines.append(
                            f"• <i>Why it matters:</i> {_safe_html(why_matters, max_chars=260)}"
                        )

                    source_hint = str(fact.get("source_hint", "")).strip()
                    if source_hint:
                        fact_lines.append(
                            f"• <i>Source hint:</i> {_safe_html(source_hint, max_chars=160)}"
                        )

                    confidence = fact.get("confidence")
                    if confidence is not None:
                        try:
                            conf_val = float(confidence)
                            fact_lines.append(f"• <i>Confidence:</i> <code>{conf_val:.0%}</code>")
                        except Exception:
                            logger.debug("confidence_score_conversion_failed", exc_info=True)
                            fact_lines.append(
                                f"• <i>Confidence:</i> <code>{html.escape(str(confidence))}</code>"
                            )

                    facts_section.append("\n".join(fact_lines))
            if facts_section:
                sections_sent = True
                lines.extend(["", "<b>📌 Fresh Facts</b>", "\n\n".join(facts_section)])

            open_questions = insights.get("open_questions")
            if isinstance(open_questions, list):
                questions = _clean_list(open_questions, limit=5)
                if questions:
                    sections_sent = True
                    lines.extend(
                        ["", "<b>❓ Open Questions</b>", "\n".join(f"• {q}" for q in questions)]
                    )

            suggested_sources = insights.get("suggested_sources")
            if isinstance(suggested_sources, list):
                sources = _clean_list(suggested_sources, limit=5, item_max_chars=260)
                if sources:
                    sections_sent = True
                    lines.extend(
                        ["", "<b>🔗 Suggested Follow-up</b>", "\n".join(f"• {s}" for s in sources)]
                    )

            expansion = insights.get("expansion_topics")
            if isinstance(expansion, list):
                exp_clean = _clean_list(expansion, limit=6)
                if exp_clean:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            "<b>🧠 Expansion Topics</b> (beyond the article)",
                            "\n".join(f"• {item}" for item in exp_clean),
                        ]
                    )

            next_steps = insights.get("next_exploration")
            if isinstance(next_steps, list):
                nxt_clean = _clean_list(next_steps, limit=6)
                if nxt_clean:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            "<b>🚀 What to explore next</b>",
                            "\n".join(f"• {step}" for step in nxt_clean),
                        ]
                    )

            caution = insights.get("caution")
            if isinstance(caution, str) and caution.strip():
                sections_sent = True
                lines.extend(["", "<b>⚠️ Caveats</b>", _safe_html(caution, max_chars=900)])

            if not sections_sent:
                await self._response_sender.safe_reply(
                    message, "No additional research insights were available."
                )
                return

            await self._text_processor.send_long_text(
                message,
                "\n".join(lines).strip(),
                parse_mode="HTML",
            )

        except Exception as exc:  # pragma: no cover - defensive
            raise_if_cancelled(exc)
            logger.error("insights_message_error", extra={"error": str(exc), "cid": correlation_id})

    async def send_custom_article(self, message: Any, article: dict[str, Any]) -> None:
        """Send the custom generated article with a nice header and downloadable JSON."""
        try:
            title = str(article.get("title", "")).strip() or "Custom Article"
            subtitle = str(article.get("subtitle", "") or "").strip()
            body = str(article.get("article_markdown", "")).strip()

            raw_highlights = article.get("highlights")
            if isinstance(raw_highlights, list):
                highlights = [str(x).strip() for x in raw_highlights if str(x).strip()]
            elif isinstance(raw_highlights, str):
                highlights = [
                    part.strip(" -•\t")
                    for part in re.split(r"[\n\r•;]+", raw_highlights)
                    if part.strip()
                ]
            elif raw_highlights is None:
                highlights = []
            else:
                highlights = [str(raw_highlights).strip()] if str(raw_highlights).strip() else []

            header_lines: list[str] = []
            title_html = html.escape(title)
            header_lines.append(f"<b>📝 {title_html}</b>")
            if subtitle:
                subtitle_html = html.escape(subtitle)
                header_lines.append(f"<i>{subtitle_html}</i>")

            await self._response_sender.safe_reply(
                message, "\n".join(header_lines), parse_mode="HTML"
            )

            if body:
                await self._text_processor.send_long_text(message, body)

            if highlights:
                await self._text_processor.send_long_text(
                    message, "⭐ Key Highlights:\n" + "\n".join([f"• {h}" for h in highlights[:10]])
                )

            await self._response_sender.reply_json(message, article)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_forward_summary_response(
        self, message: Any, forward_shaped: dict[str, Any], summary_id: int | str | None = None
    ) -> None:
        """Send forward summary with per-field messages, then attach full JSON file.

        Args:
            message: Telegram message object
            forward_shaped: Forward summary data dictionary
            summary_id: Database summary ID for action buttons (optional)
        """
        try:
            # Finalize progress tracker -- edit the progress message into the final header
            if self._progress_tracker is not None:
                result = await self._progress_tracker.finalize(
                    message,
                    "Forward Summary Ready",
                )
                if result is None:
                    logger.warning(
                        "forward_progress_finalize_failed",
                        extra={"request_message_id": getattr(message, "id", None)},
                    )
            else:
                await self._response_sender.safe_reply(message, "Forward Summary Ready")

            combined_lines: list[str] = []
            tl_dr = str(forward_shaped.get("summary_250", "")).strip()
            if tl_dr:
                tl_dr_clean = self._text_processor.sanitize_summary_text(tl_dr)
                combined_lines.extend(["📋 TL;DR:", tl_dr_clean, ""])

            tags = [
                str(t).strip() for t in (forward_shaped.get("topic_tags") or []) if str(t).strip()
            ]
            if tags:
                shown = tags[:5]
                hidden = max(0, len(tags) - len(shown))
                tail = f" (+{hidden})" if hidden else ""
                combined_lines.append("🏷️ Tags: " + " ".join(shown) + tail)
                combined_lines.append("")

            entities = forward_shaped.get("entities") or {}
            if isinstance(entities, dict):
                people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
                orgs = [
                    str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()
                ]
                locs = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]
                if people or orgs or locs:
                    combined_lines.append("🧭 Entities:")
                    if people:
                        shown = people[:5]
                        hidden = max(0, len(people) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• People: " + ", ".join(shown) + tail)
                    if orgs:
                        shown = orgs[:5]
                        hidden = max(0, len(orgs) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• Orgs: " + ", ".join(shown) + tail)
                    if locs:
                        shown = locs[:5]
                        hidden = max(0, len(locs) - len(shown))
                        tail = f" (+{hidden})" if hidden else ""
                        combined_lines.append("• Places: " + ", ".join(shown) + tail)
                    combined_lines.append("")

            reading_time = forward_shaped.get("estimated_reading_time_min")
            if reading_time:
                combined_lines.append(f"⏱️ Reading time: ~{reading_time} min")
                combined_lines.append("")

            key_stats = forward_shaped.get("key_stats") or []
            if isinstance(key_stats, list) and key_stats:
                ks_lines = self._data_formatter.format_key_stats(key_stats[:10])
                if ks_lines:
                    combined_lines.append("📈 Key Stats:")
                    combined_lines.extend(ks_lines)
                    combined_lines.append("")

            readability = forward_shaped.get("readability") or {}
            readability_line = self._data_formatter.format_readability(readability)
            if readability_line:
                combined_lines.append(f"🧮 Readability — {readability_line}")
                combined_lines.append("")

            # Metadata for forward posts
            metadata = forward_shaped.get("metadata") or {}
            if isinstance(metadata, dict):
                meta_parts = []
                if metadata.get("title"):
                    meta_parts.append(f"📰 {metadata['title']}")
                if metadata.get("author"):
                    meta_parts.append(f"✍️ {metadata['author']}")
                if meta_parts:
                    combined_lines.extend(meta_parts)
                    combined_lines.append("")

            # Categories & Risk for forwards
            categories = [
                str(c).strip() for c in (forward_shaped.get("categories") or []) if str(c).strip()
            ]
            if categories:
                combined_lines.append("📁 Categories: " + ", ".join(categories[:10]))
                combined_lines.append("")

            confidence = forward_shaped.get("confidence", 1.0)
            risk = forward_shaped.get("hallucination_risk", "low")
            if isinstance(confidence, int | float) and confidence < 1.0:
                combined_lines.append(f"🎯 Confidence: {confidence:.1%}")
            if risk != "low":
                risk_emoji = "⚠️" if risk == "med" else "🚨"
                combined_lines.append(f"{risk_emoji} Hallucination risk: {risk}")
            if confidence < 1.0 or risk != "low":
                combined_lines.append("")

            if combined_lines:
                # Remove trailing empty lines
                while combined_lines and not combined_lines[-1]:
                    combined_lines.pop()
                await self._text_processor.send_long_text(message, "\n".join(combined_lines))

            # Separated summary fields
            summary_fields = [
                k
                for k in forward_shaped
                if k.startswith("summary_") and k.split("_", 1)[1].isdigit()
            ]

            def _key_num_f(k: str) -> int:
                try:
                    return int(k.split("_", 1)[1])
                except Exception:
                    logger.debug("sort_key_extraction_failed", exc_info=True)
                    return 0

            for key in sorted(summary_fields, key=_key_num_f):
                content = str(forward_shaped.get(key, "")).strip()
                if content:
                    content = self._text_processor.sanitize_summary_text(content)
                    await self._text_processor.send_labelled_text(
                        message,
                        f"🧾 Summary {key.split('_', 1)[1]}",
                        content,
                    )

            ideas = [
                str(x).strip() for x in (forward_shaped.get("key_ideas") or []) if str(x).strip()
            ]
            if ideas:
                await self._text_processor.send_long_text(
                    message,
                    "<b>💡 Key Ideas</b>\n" + "\n".join([f"• {i}" for i in ideas]),
                    parse_mode="HTML",
                )

            # Send new field messages for forwards
            await self._send_new_field_messages(message, forward_shaped)
        except Exception as exc:
            raise_if_cancelled(exc)

        await self._response_sender.reply_json(message, forward_shaped)

        # Add action buttons after forward summary if summary_id is available
        if summary_id:
            await self._send_action_buttons(message, summary_id)

    async def _send_new_field_messages(self, message: Any, shaped: dict[str, Any]) -> None:
        """Send messages for new fields like extractive quotes, highlights, etc."""
        try:
            # Extractive quotes with HTML blockquotes
            quotes = shaped.get("extractive_quotes") or []
            if isinstance(quotes, list) and quotes:
                quote_lines = ["<b>💬 Key Quotes</b>"]
                for i, quote in enumerate(quotes[:5], 1):
                    if isinstance(quote, dict) and quote.get("text"):
                        text = str(quote["text"]).strip()
                        if text:
                            escaped_text = html.escape(text)
                            quote_lines.append(f"<blockquote>{i}. {escaped_text}</blockquote>")
                if len(quote_lines) > 1:
                    await self._text_processor.send_long_text(
                        message, "\n".join(quote_lines), parse_mode="HTML"
                    )

            highlights = [
                str(h).strip() for h in (shaped.get("highlights") or []) if str(h).strip()
            ]
            if highlights:
                await self._text_processor.send_long_text(
                    message,
                    "<b>✨ Highlights</b>\n" + "\n".join([f"• {h}" for h in highlights[:10]]),
                    parse_mode="HTML",
                )

            # Questions answered (as Q&A pairs) with HTML formatting
            questions_answered = shaped.get("questions_answered") or []
            if isinstance(questions_answered, list) and questions_answered:
                qa_lines = ["<b>❓ Questions Answered</b>"]
                for i, qa in enumerate(questions_answered[:10], 1):
                    if isinstance(qa, dict):
                        question = str(qa.get("question", "")).strip()
                        answer = str(qa.get("answer", "")).strip()
                        if question:
                            escaped_question = html.escape(question)
                            qa_lines.append(f"\n{i}. <b>Q:</b> {escaped_question}")
                            if answer:
                                escaped_answer = html.escape(answer)
                                qa_lines.append(f"   <b>A:</b> {escaped_answer}")
                            else:
                                qa_lines.append("   <b>A:</b> <i>(No answer provided)</i>")
                if len(qa_lines) > 1:
                    await self._text_processor.send_long_text(
                        message, "\n".join(qa_lines), parse_mode="HTML"
                    )

            # Key points to remember
            key_points = [
                str(kp).strip()
                for kp in (shaped.get("key_points_to_remember") or [])
                if str(kp).strip()
            ]
            if key_points:
                await self._text_processor.send_long_text(
                    message,
                    "<b>🎯 Key Points to Remember</b>\n"
                    + "\n".join([f"• {kp}" for kp in key_points[:10]]),
                    parse_mode="HTML",
                )

            # Insights: Caution/Caveats
            insights = shaped.get("insights")
            if isinstance(insights, dict):
                caution = str(insights.get("caution") or "").strip()
                if caution:
                    await self._text_processor.send_long_text(
                        message,
                        f"<b>⚠️ Caveats</b>\n{html.escape(caution)}",
                        parse_mode="HTML",
                    )

                critique = insights.get("critique")
                if isinstance(critique, list) and critique:
                    crit_lines = [
                        f"• {html.escape(str(c).strip())}" for c in critique if str(c).strip()
                    ]
                    if crit_lines:
                        await self._text_processor.send_long_text(
                            message,
                            "<b>🤔 Critical Analysis</b>\n" + "\n".join(crit_lines[:5]),
                            parse_mode="HTML",
                        )

            # Perspective & Quality
            quality = shaped.get("quality")
            if isinstance(quality, dict):
                q_lines = []
                bias = str(quality.get("author_bias") or "").strip()
                tone = str(quality.get("emotional_tone") or "").strip()
                evidence = str(quality.get("evidence_quality") or "").strip()
                missing = quality.get("missing_perspectives")

                if bias:
                    q_lines.append(f"• <b>Bias:</b> {html.escape(bias)}")
                if tone:
                    q_lines.append(f"• <b>Tone:</b> {html.escape(tone)}")
                if evidence:
                    q_lines.append(f"• <b>Evidence:</b> {html.escape(evidence)}")

                if isinstance(missing, list) and missing:
                    clean_missing = [str(m).strip() for m in missing if str(m).strip()]
                    if clean_missing:
                        q_lines.append("• <b>Missing Context:</b>")
                        for m in clean_missing[:3]:
                            q_lines.append(f"  - {html.escape(m)}")

                if q_lines:
                    await self._text_processor.send_long_text(
                        message,
                        "<b>⚖️ Perspective & Quality</b>\n" + "\n".join(q_lines),
                        parse_mode="HTML",
                    )

            # Topic taxonomy (if present and not empty)
            taxonomy = shaped.get("topic_taxonomy") or []
            if isinstance(taxonomy, list) and taxonomy:
                tax_lines = ["<b>🏷️ Topic Classification</b>"]
                for tax in taxonomy[:5]:
                    if isinstance(tax, dict) and tax.get("label"):
                        label = str(tax["label"]).strip()
                        score = tax.get("score", 0.0)
                        if isinstance(score, int | float) and score > 0:
                            tax_lines.append(f"• {label} ({score:.1%})")
                        else:
                            tax_lines.append(f"• {label}")
                if len(tax_lines) > 1:
                    await self._text_processor.send_long_text(
                        message, "\n".join(tax_lines), parse_mode="HTML"
                    )

            # Forwarded post extras
            fwd_extras = shaped.get("forwarded_post_extras")
            if isinstance(fwd_extras, dict):
                fwd_parts = []
                if fwd_extras.get("channel_title"):
                    fwd_parts.append(f"📺 Channel: {fwd_extras['channel_title']}")
                if fwd_extras.get("channel_username"):
                    fwd_parts.append(f"@{fwd_extras['channel_username']}")
                hashtags = [
                    str(h).strip() for h in (fwd_extras.get("hashtags") or []) if str(h).strip()
                ]
                if hashtags:
                    fwd_parts.append(
                        "Tags: "
                        + " ".join([f"#{h}" if not h.startswith("#") else h for h in hashtags[:5]])
                    )
                if fwd_parts:
                    await self._text_processor.send_long_text(
                        message,
                        "<b>📤 Forward Info</b>\n" + "\n".join(fwd_parts),
                        parse_mode="HTML",
                    )

        except Exception as exc:
            raise_if_cancelled(exc)
