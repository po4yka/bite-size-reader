"""Summary presentation formatting."""

from __future__ import annotations

import html
import logging
import re
from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting.summary.action_buttons import (
    create_action_buttons,
    create_inline_keyboard,
)
from app.adapters.external.formatting.summary.card_renderer import (
    build_compact_card_html,
    compact_tldr,
    extract_domain_from_url,
    truncate_plain_text,
)
from app.adapters.external.formatting.summary.crosspost_publisher import crosspost_to_topic
from app.adapters.external.formatting.summary.related_reads_presenter import (
    send_related_reads as present_related_reads,
)
from app.core.async_utils import raise_if_cancelled
from app.core.ui_strings import t

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import (
        DataFormatter,
        ResponseSender,
        TextProcessor,
    )
    from app.adapters.telegram.topic_manager import TopicManager
    from app.application.services.related_reads_service import RelatedReadItem
    from app.core.progress_tracker import ProgressTracker
    from app.core.verbosity import VerbosityResolver

logger = logging.getLogger(__name__)


class SummaryPresenterImpl:
    """Implementation of summary presentation."""

    @staticmethod
    def _truncate_plain_text(text: str, max_len: int) -> str:
        return truncate_plain_text(text, max_len)

    @staticmethod
    def _extract_domain_from_url(url: str) -> str | None:
        return extract_domain_from_url(url)

    def _compact_tldr(self, text: str, *, max_sentences: int = 3, max_chars: int = 520) -> str:
        """Return the first 2-3 sentences (best-effort) for the card TL;DR."""
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
        return build_compact_card_html(
            summary_shaped,
            llm,
            chunks,
            reader=reader,
            text_processor=self._text_processor,
            data_formatter=self._data_formatter,
            lang=self._lang,
        )

    def __init__(
        self,
        response_sender: ResponseSender,
        text_processor: TextProcessor,
        data_formatter: DataFormatter,
        *,
        verbosity_resolver: VerbosityResolver | None = None,
        progress_tracker: ProgressTracker | None = None,
        topic_manager: TopicManager | None = None,
        lang: str = "en",
    ) -> None:
        self._response_sender = response_sender
        self._text_processor = text_processor
        self._data_formatter = data_formatter
        self._verbosity_resolver = verbosity_resolver
        self._progress_tracker = progress_tracker
        self._topic_manager = topic_manager
        self._lang = lang

    def set_topic_manager(self, topic_manager: TopicManager | None) -> None:
        """Update forum-topic routing without rebuilding the presenter."""
        self._topic_manager = topic_manager

    def _create_action_buttons(self, summary_id: int | str) -> list[list[dict[str, str]]]:
        """Create inline keyboard buttons for post-summary actions.

        Returns a 2D list of button rows for InlineKeyboardMarkup.
        """
        return create_action_buttons(summary_id, lang=self._lang)

    def _create_inline_keyboard(
        self, summary_id: int | str, correlation_id: str | None = None
    ) -> Any:
        """Create an inline keyboard markup for post-summary actions."""
        return create_inline_keyboard(summary_id, correlation_id, lang=self._lang)

    async def _send_action_buttons(
        self, message: Any, summary_id: int | str, correlation_id: str | None = None
    ) -> int | None:
        """Send action buttons as a separate message after the summary.

        Returns the Telegram message ID of the sent message, or None if not sent.
        """
        try:
            keyboard = self._create_inline_keyboard(summary_id, correlation_id)
            if keyboard:
                msg_id = await self._response_sender.safe_reply_with_id(
                    message,
                    t("quick_actions", self._lang),
                    reply_markup=keyboard,
                )
                logger.debug(
                    "action_buttons_sent",
                    extra={"summary_id": summary_id},
                )
                return msg_id
        except Exception as e:
            raise_if_cancelled(e)
            logger.warning(
                "send_action_buttons_failed",
                extra={"summary_id": summary_id, "error": str(e)},
            )
        return None

    async def _is_reader_mode(self, message: Any) -> bool:
        if self._verbosity_resolver is None:
            return False
        from app.core.verbosity import VerbosityLevel

        return (await self._verbosity_resolver.get_verbosity(message)) == VerbosityLevel.READER

    async def _finalize_compact_card(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None,
        summary_id: int | str | None,
        *,
        reader: bool,
    ) -> tuple[bool, str | None]:
        card_text: str | None = None
        try:
            card_text = self._build_compact_card_html(summary_shaped, llm, chunks, reader=reader)
            if self._progress_tracker is None:
                return False, card_text

            keyboard = self._create_inline_keyboard(summary_id) if summary_id else None
            result = await self._progress_tracker.finalize(
                message,
                card_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            if result is not None:
                return True, card_text
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
        return False, card_text

    async def _send_structured_header(self, message: Any, llm: Any, chunks: int | None) -> None:
        method = (
            f"{t('chunked', self._lang)} ({chunks} parts)"
            if chunks
            else t("single_pass", self._lang)
        )
        model_name = getattr(llm, "model", None)
        header = (
            f"{t('summary_ready', self._lang)}\n"
            f"{t('model', self._lang)}: {model_name or 'unknown'}\n"
            f"Method: {method}"
        )
        await self._response_sender.safe_reply(message, header)

    @staticmethod
    def _trim_trailing_blank_lines(lines: list[str]) -> list[str]:
        while lines and not lines[-1]:
            lines.pop()
        return lines

    @staticmethod
    def _clean_string_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(v).strip() for v in values if str(v).strip()]

    @staticmethod
    def _summarize_visible_items(items: list[str], limit: int, *, joiner: str) -> str:
        shown = items[:limit]
        hidden = max(0, len(items) - len(shown))
        tail = f" (+{hidden})" if hidden else ""
        return joiner.join(shown) + tail

    def _build_combined_summary_lines(
        self, shaped: dict[str, Any], *, include_domain: bool
    ) -> list[str]:
        _l = self._lang
        combined_lines: list[str] = []

        tl_dr = str(shaped.get("summary_250", "")).strip()
        if tl_dr:
            tl_dr_clean = self._text_processor.sanitize_summary_text(tl_dr)
            combined_lines.extend([f"\U0001f4cb {t('tldr', _l)}:", tl_dr_clean, ""])

        tag_items = self._clean_string_list(shaped.get("topic_tags") or [])
        if tag_items:
            combined_lines.append(
                f"\U0001f3f7\ufe0f {t('tags', _l)}: "
                + self._summarize_visible_items(tag_items, 5, joiner=" ")
            )
            combined_lines.append("")

        entities = shaped.get("entities") or {}
        if isinstance(entities, dict):
            people = self._clean_string_list(entities.get("people") or [])
            orgs = self._clean_string_list(entities.get("organizations") or [])
            locs = self._clean_string_list(entities.get("locations") or [])
            if people or orgs or locs:
                combined_lines.append(f"\U0001f9ed {t('entities', _l)}:")
                if people:
                    combined_lines.append(
                        f"\u2022 {t('people', _l)}: "
                        + self._summarize_visible_items(people, 5, joiner=", ")
                    )
                if orgs:
                    combined_lines.append(
                        f"\u2022 {t('orgs', _l)}: "
                        + self._summarize_visible_items(orgs, 5, joiner=", ")
                    )
                if locs:
                    combined_lines.append(
                        f"\u2022 {t('places', _l)}: "
                        + self._summarize_visible_items(locs, 5, joiner=", ")
                    )
                combined_lines.append("")

        reading_time = shaped.get("estimated_reading_time_min")
        if reading_time:
            combined_lines.append(f"\u23f1\ufe0f {t('reading_time', _l)}: ~{reading_time} min")
            combined_lines.append("")

        key_stats = shaped.get("key_stats") or []
        if isinstance(key_stats, list) and key_stats:
            ks_lines = self._data_formatter.format_key_stats(key_stats[:10])
            if ks_lines:
                combined_lines.append(f"\U0001f4c8 {t('key_stats', _l)}:")
                combined_lines.extend(ks_lines)
                combined_lines.append("")

        readability = shaped.get("readability") or {}
        readability_line = self._data_formatter.format_readability(readability)
        if readability_line:
            combined_lines.append(f"\U0001f9ee {t('readability', _l)} \u2014 {readability_line}")
            combined_lines.append("")

        metadata = shaped.get("metadata") or {}
        if isinstance(metadata, dict):
            meta_parts = []
            if metadata.get("title"):
                meta_parts.append(f"📰 {metadata['title']}")
            if metadata.get("author"):
                meta_parts.append(f"✍️ {metadata['author']}")
            if include_domain and metadata.get("domain"):
                meta_parts.append(f"🌐 {metadata['domain']}")
            if meta_parts:
                combined_lines.extend(meta_parts)
                combined_lines.append("")

        categories = self._clean_string_list(shaped.get("categories") or [])
        if categories:
            combined_lines.append(
                f"\U0001f4c1 {t('categories', _l)}: " + ", ".join(categories[:10])
            )
            combined_lines.append("")

        confidence = shaped.get("confidence", 1.0)
        low_confidence = isinstance(confidence, (int, float)) and confidence < 1.0
        risk = str(shaped.get("hallucination_risk", "low"))
        if low_confidence:
            combined_lines.append(f"\U0001f3af {t('confidence', _l)}: {confidence:.1%}")
        if risk != "low":
            risk_emoji = "\u26a0\ufe0f" if risk == "med" else "\U0001f6a8"
            combined_lines.append(f"{risk_emoji} {t('hallucination_risk', _l)}: {risk}")
        if low_confidence or risk != "low":
            combined_lines.append("")

        return self._trim_trailing_blank_lines(combined_lines)

    async def _send_combined_summary_lines(
        self, message: Any, shaped: dict[str, Any], *, include_domain: bool
    ) -> None:
        combined_lines = self._build_combined_summary_lines(shaped, include_domain=include_domain)
        if combined_lines:
            await self._text_processor.send_long_text(message, "\n".join(combined_lines))

    @staticmethod
    def _summary_sort_key(field_name: str) -> int:
        if field_name == "tldr":
            return 10_000
        try:
            return int(field_name.split("_", 1)[1])
        except Exception:
            logger.debug("sort_key_extraction_failed", exc_info=True)
            return 0

    @staticmethod
    def _summary_field_keys(shaped: dict[str, Any], *, include_tldr: bool) -> list[str]:
        fields = [
            key
            for key in shaped
            if (key.startswith("summary_") and key.split("_", 1)[1].isdigit())
            or (include_tldr and key == "tldr")
        ]
        return sorted(fields, key=SummaryPresenterImpl._summary_sort_key)

    async def _send_summary_fields(
        self, message: Any, shaped: dict[str, Any], *, include_tldr: bool
    ) -> None:
        _l = self._lang
        for key in self._summary_field_keys(shaped, include_tldr=include_tldr):
            content = str(shaped.get(key, "")).strip()
            if not content:
                continue
            content = self._text_processor.sanitize_summary_text(content)
            label = f"\U0001f9fe {t('tldr', _l)}"
            if key != "tldr":
                label = f"\U0001f9fe {t('summary_n', _l)} {key.split('_', 1)[1]}"
            await self._text_processor.send_labelled_text(message, label, content)

    async def _send_key_ideas(self, message: Any, shaped: dict[str, Any]) -> None:
        ideas = self._clean_string_list(shaped.get("key_ideas") or [])
        if not ideas:
            return

        chunk: list[str] = []
        for idea in ideas:
            chunk.append(f"• {idea}")
            if sum(len(line) + 1 for line in chunk) > 3000:
                await self._text_processor.send_long_text(
                    message,
                    f"<b>\U0001f4a1 {t('key_ideas', self._lang)}</b>\n" + "\n".join(chunk),
                    parse_mode="HTML",
                )
                chunk = []

        if chunk:
            await self._text_processor.send_long_text(
                message,
                f"<b>\U0001f4a1 {t('key_ideas', self._lang)}</b>\n" + "\n".join(chunk),
                parse_mode="HTML",
            )

    async def send_structured_summary_response(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None = None,
        summary_id: int | str | None = None,
        correlation_id: str | None = None,
    ) -> int | None:
        """Send summary where each top-level JSON field is a separate message,
        then attach the full JSON as a .json document with a descriptive filename.

        Args:
            message: Telegram message object
            summary_shaped: Summary data dictionary
            llm: LLM instance (for model name)
            chunks: Number of chunks used (optional)
            summary_id: Database summary ID for action buttons (optional)
            correlation_id: Request correlation ID for tracing (optional)

        Returns:
            The Telegram message ID of the last sent message (action buttons), or None.
        """
        try:
            reader = await self._is_reader_mode(message)
            job_card_finalized, card_text = await self._finalize_compact_card(
                message,
                summary_shaped,
                llm,
                chunks,
                summary_id,
                reader=reader,
            )

            if reader and job_card_finalized:
                return None

            if not reader and not job_card_finalized:
                try:
                    await self._send_structured_header(message, llm, chunks)
                except Exception as exc:
                    raise_if_cancelled(exc)

            if not job_card_finalized:
                await self._send_combined_summary_lines(
                    message, summary_shaped, include_domain=True
                )

            await self._send_summary_fields(
                message, summary_shaped, include_tldr=not job_card_finalized
            )
            await self._send_key_ideas(message, summary_shaped)
            await self._send_new_field_messages(message, summary_shaped)
            await self._response_sender.reply_json(message, summary_shaped)

            bot_reply_id: int | None = None
            if summary_id and not job_card_finalized:
                bot_reply_id = await self._send_action_buttons(message, summary_id, correlation_id)

            await self._crosspost_to_topic(
                message, summary_shaped, llm, chunks, summary_id, correlation_id, card_text
            )
            return bot_reply_id
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
            return None

    async def _crosspost_to_topic(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None,
        summary_id: int | str | None,
        correlation_id: str | None,
        card_text: str | None = None,
    ) -> None:
        """Delegate to crosspost module for forum topic routing."""
        if self._topic_manager is None:
            return
        if card_text is None:
            card_text = self._build_compact_card_html(summary_shaped, llm, chunks, reader=True)
        await crosspost_to_topic(
            topic_manager=self._topic_manager,
            response_sender=self._response_sender,
            message=message,
            summary_shaped=summary_shaped,
            summary_id=summary_id,
            correlation_id=correlation_id,
            card_text=card_text,
            create_keyboard_fn=self._create_inline_keyboard,
        )

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

    def _insights_cap_text(self, text: str, max_chars: int) -> str:
        cleaned = self._text_processor.sanitize_summary_text(text.strip())
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max(0, max_chars - 1)].rstrip() + "…"

    def _insights_safe_html(self, text: str, *, max_chars: int = 900) -> str:
        return self._text_processor.linkify_urls(
            html.escape(self._insights_cap_text(text, max_chars))
        )

    def _insights_clean_list(
        self, items: list[Any], *, limit: int, item_max_chars: int = 220
    ) -> list[str]:
        cleaned: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            cleaned.append(self._insights_safe_html(text, max_chars=item_max_chars))
            if len(cleaned) >= limit:
                break
        return cleaned

    def _build_new_facts_section(self, insights: dict[str, Any]) -> list[str]:
        facts_section: list[str] = []
        facts = insights.get("new_facts")
        if not isinstance(facts, list):
            return facts_section

        _l = self._lang
        for idx, fact in enumerate(facts[:5], start=1):
            if not isinstance(fact, dict):
                continue
            fact_text = str(fact.get("fact", "")).strip()
            if not fact_text:
                continue

            fact_lines = [f"<b>{idx}.</b> {self._insights_safe_html(fact_text, max_chars=320)}"]
            why_matters = str(fact.get("why_it_matters", "")).strip()
            if why_matters:
                fact_lines.append(
                    f"\u2022 <i>{t('why_matters', _l)}:</i> "
                    f"{self._insights_safe_html(why_matters, max_chars=260)}"
                )

            source_hint = str(fact.get("source_hint", "")).strip()
            if source_hint:
                fact_lines.append(
                    f"\u2022 <i>{t('source_hint', _l)}:</i> "
                    f"{self._insights_safe_html(source_hint, max_chars=160)}"
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
        return facts_section

    async def send_additional_insights_message(
        self, message: Any, insights: dict[str, Any], correlation_id: str | None = None
    ) -> None:
        """Send follow-up message summarizing additional research insights."""
        try:
            if await self._is_reader_mode(message):
                return
            _l = self._lang
            lines: list[str] = [f"<b>\U0001f50e {t('research_highlights', _l)}</b>"]
            if correlation_id:
                lines.append(
                    f"<i>Correlation ID:</i> <code>{html.escape(str(correlation_id))}</code>"
                )

            sections_sent = False

            overview = insights.get("topic_overview")
            if isinstance(overview, str) and overview.strip():
                sections_sent = True
                lines.extend(
                    [
                        "",
                        f"<b>\U0001f9ed {t('overview', _l)}</b>",
                        self._insights_safe_html(overview, max_chars=1200),
                    ]
                )

            facts_section = self._build_new_facts_section(insights)
            if facts_section:
                sections_sent = True
                lines.extend(
                    ["", f"<b>\U0001f4cc {t('fresh_facts', _l)}</b>", "\n\n".join(facts_section)]
                )

            open_questions = insights.get("open_questions")
            if isinstance(open_questions, list):
                questions = self._insights_clean_list(open_questions, limit=5)
                if questions:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            f"<b>\u2753 {t('open_questions', _l)}</b>",
                            "\n".join(f"\u2022 {q}" for q in questions),
                        ]
                    )

            suggested_sources = insights.get("suggested_sources")
            if isinstance(suggested_sources, list):
                sources = self._insights_clean_list(suggested_sources, limit=5, item_max_chars=260)
                if sources:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            f"<b>\U0001f517 {t('suggested_followup', _l)}</b>",
                            "\n".join(f"\u2022 {s}" for s in sources),
                        ]
                    )

            expansion = insights.get("expansion_topics")
            if isinstance(expansion, list):
                exp_clean = self._insights_clean_list(expansion, limit=6)
                if exp_clean:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            f"<b>\U0001f9e0 {t('expansion_topics', _l)}</b> ({t('beyond_article', _l)})",
                            "\n".join(f"\u2022 {item}" for item in exp_clean),
                        ]
                    )

            next_steps = insights.get("next_exploration")
            if isinstance(next_steps, list):
                nxt_clean = self._insights_clean_list(next_steps, limit=6)
                if nxt_clean:
                    sections_sent = True
                    lines.extend(
                        [
                            "",
                            f"<b>\U0001f680 {t('explore_next', _l)}</b>",
                            "\n".join(f"\u2022 {step}" for step in nxt_clean),
                        ]
                    )

            caution = insights.get("caution")
            if isinstance(caution, str) and caution.strip():
                sections_sent = True
                lines.extend(
                    [
                        "",
                        f"<b>\u26a0\ufe0f {t('caveats', _l)}</b>",
                        self._insights_safe_html(caution, max_chars=900),
                    ]
                )

            if not sections_sent:
                await self._response_sender.safe_reply(message, t("no_insights", _l))
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
                    message,
                    f"\u2b50 {t('key_highlights', self._lang)}:\n"
                    + "\n".join([f"\u2022 {h}" for h in highlights[:10]]),
                )

            await self._response_sender.reply_json(message, article)
        except Exception as exc:
            raise_if_cancelled(exc)

    async def send_related_reads(
        self,
        message: Any,
        items: list[RelatedReadItem],
        *,
        lang: str | None = None,
    ) -> None:
        """Send related-read shortcuts as a follow-up keyboard."""
        await present_related_reads(
            self._response_sender,
            message,
            items,
            lang or self._lang,
        )

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
            _l = self._lang
            if self._progress_tracker is not None:
                result = await self._progress_tracker.finalize(
                    message, t("forward_summary_ready", _l)
                )
                if result is None:
                    logger.warning(
                        "forward_progress_finalize_failed",
                        extra={"request_message_id": getattr(message, "id", None)},
                    )
            else:
                await self._response_sender.safe_reply(message, t("forward_summary_ready", _l))

            await self._send_combined_summary_lines(message, forward_shaped, include_domain=False)
            await self._send_summary_fields(message, forward_shaped, include_tldr=False)
            await self._send_key_ideas(message, forward_shaped)
            await self._send_new_field_messages(message, forward_shaped)
        except Exception as exc:
            raise_if_cancelled(exc)

        await self._response_sender.reply_json(message, forward_shaped)
        if summary_id:
            await self._send_action_buttons(message, summary_id)

    def _build_extractive_quotes_message(self, shaped: dict[str, Any]) -> str | None:
        quotes = shaped.get("extractive_quotes") or []
        if not isinstance(quotes, list) or not quotes:
            return None
        lines = [f"<b>\U0001f4ac {t('key_quotes', self._lang)}</b>"]
        for i, quote in enumerate(quotes[:5], 1):
            if not isinstance(quote, dict) or not quote.get("text"):
                continue
            text = str(quote["text"]).strip()
            if text:
                lines.append(f"<blockquote>{i}. {html.escape(text)}</blockquote>")
        return "\n".join(lines) if len(lines) > 1 else None

    def _build_bullet_message(
        self, title: str, values: list[str], *, limit: int, escape: bool = False
    ) -> str | None:
        if not values:
            return None
        items = values[:limit]
        if escape:
            items = [html.escape(item) for item in items]
        return title + "\n" + "\n".join(f"\u2022 {item}" for item in items)

    def _build_questions_answered_message(self, shaped: dict[str, Any]) -> str | None:
        questions_answered = shaped.get("questions_answered") or []
        if not isinstance(questions_answered, list) or not questions_answered:
            return None

        qa_lines = [f"<b>\u2753 {t('questions_answered', self._lang)}</b>"]
        for i, qa in enumerate(questions_answered[:10], 1):
            if not isinstance(qa, dict):
                continue
            question = str(qa.get("question", "")).strip()
            if not question:
                continue
            answer = str(qa.get("answer", "")).strip()
            qa_lines.append(f"\n{i}. <b>Q:</b> {html.escape(question)}")
            if answer:
                qa_lines.append(f"   <b>A:</b> {html.escape(answer)}")
            else:
                qa_lines.append(f"   <b>A:</b> <i>{t('no_answer', self._lang)}</i>")
        return "\n".join(qa_lines) if len(qa_lines) > 1 else None

    def _build_insights_messages(self, shaped: dict[str, Any]) -> list[str]:
        insights = shaped.get("insights")
        if not isinstance(insights, dict):
            return []

        messages: list[str] = []
        caution = str(insights.get("caution") or "").strip()
        if caution:
            messages.append(
                f"<b>\u26a0\ufe0f {t('caveats', self._lang)}</b>\n{html.escape(caution)}"
            )

        critique = insights.get("critique")
        if isinstance(critique, list) and critique:
            crit_lines = [f"• {html.escape(str(c).strip())}" for c in critique if str(c).strip()]
            if crit_lines:
                messages.append(
                    f"<b>\U0001f914 {t('critical_analysis', self._lang)}</b>\n"
                    + "\n".join(crit_lines[:5])
                )
        return messages

    def _build_quality_message(self, shaped: dict[str, Any]) -> str | None:
        quality = shaped.get("quality")
        if not isinstance(quality, dict):
            return None

        _l = self._lang
        lines: list[str] = []
        bias = str(quality.get("author_bias") or "").strip()
        tone = str(quality.get("emotional_tone") or "").strip()
        evidence = str(quality.get("evidence_quality") or "").strip()
        missing = quality.get("missing_perspectives")

        if bias:
            lines.append(f"\u2022 <b>{t('bias', _l)}:</b> {html.escape(bias)}")
        if tone:
            lines.append(f"\u2022 <b>{t('tone', _l)}:</b> {html.escape(tone)}")
        if evidence:
            lines.append(f"\u2022 <b>{t('evidence', _l)}:</b> {html.escape(evidence)}")
        if isinstance(missing, list) and missing:
            clean_missing = [str(m).strip() for m in missing if str(m).strip()]
            if clean_missing:
                lines.append(f"\u2022 <b>{t('missing_context', _l)}:</b>")
                lines.extend(f"  - {html.escape(item)}" for item in clean_missing[:3])

        if not lines:
            return None
        return f"<b>\u2696\ufe0f {t('perspective_quality', _l)}</b>\n" + "\n".join(lines)

    def _build_taxonomy_message(self, shaped: dict[str, Any]) -> str | None:
        taxonomy = shaped.get("topic_taxonomy") or []
        if not isinstance(taxonomy, list) or not taxonomy:
            return None

        lines = [f"<b>\U0001f3f7\ufe0f {t('topic_classification', self._lang)}</b>"]
        for tax in taxonomy[:5]:
            if not isinstance(tax, dict) or not tax.get("label"):
                continue
            label = str(tax["label"]).strip()
            score = tax.get("score", 0.0)
            if isinstance(score, (int, float)) and score > 0:
                lines.append(f"• {label} ({score:.1%})")
            else:
                lines.append(f"• {label}")
        return "\n".join(lines) if len(lines) > 1 else None

    def _build_forward_extras_message(self, shaped: dict[str, Any]) -> str | None:
        fwd_extras = shaped.get("forwarded_post_extras")
        if not isinstance(fwd_extras, dict):
            return None

        _l = self._lang
        fwd_parts: list[str] = []
        if fwd_extras.get("channel_title"):
            fwd_parts.append(f"📺 Channel: {fwd_extras['channel_title']}")
        if fwd_extras.get("channel_username"):
            fwd_parts.append(f"@{fwd_extras['channel_username']}")
        hashtags = self._clean_string_list(fwd_extras.get("hashtags") or [])
        if hashtags:
            fwd_parts.append(
                f"{t('tags', _l)}: "
                + " ".join(f"#{h}" if not h.startswith("#") else h for h in hashtags[:5])
            )
        if not fwd_parts:
            return None
        return f"<b>\U0001f4e4 {t('forward_info', _l)}</b>\n" + "\n".join(fwd_parts)

    async def _send_new_field_messages(self, message: Any, shaped: dict[str, Any]) -> None:
        """Send messages for new fields like extractive quotes, highlights, and taxonomy."""
        try:
            _l = self._lang
            html_blocks = [
                self._build_extractive_quotes_message(shaped),
                self._build_bullet_message(
                    f"<b>\u2728 {t('highlights', _l)}</b>",
                    self._clean_string_list(shaped.get("highlights") or []),
                    limit=10,
                ),
                self._build_questions_answered_message(shaped),
                self._build_bullet_message(
                    f"<b>\U0001f3af {t('key_points', _l)}</b>",
                    self._clean_string_list(shaped.get("key_points_to_remember") or []),
                    limit=10,
                ),
                self._build_quality_message(shaped),
                self._build_taxonomy_message(shaped),
                self._build_forward_extras_message(shaped),
            ]

            for block in html_blocks:
                if block:
                    await self._text_processor.send_long_text(message, block, parse_mode="HTML")

            for block in self._build_insights_messages(shaped):
                await self._text_processor.send_long_text(message, block, parse_mode="HTML")
        except Exception as exc:
            raise_if_cancelled(exc)
