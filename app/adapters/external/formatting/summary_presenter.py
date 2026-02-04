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
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if max_len <= 0 or len(text) <= max_len:
            return text

        # Try to cut on a word boundary near the end for nicer output
        soft_min = max(0, int(max_len * 0.7))
        cut = text.rfind(" ", soft_min, max_len)
        if cut == -1:
            cut = max_len
        return text[:cut].rstrip() + "…"

    @staticmethod
    def _extract_domain_from_url(url: str) -> str | None:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = (parsed.netloc or "").strip()
            return host or None
        except Exception:
            return None

    def _compact_tldr(self, text: str, *, max_sentences: int = 3, max_chars: int = 520) -> str:
        """Return the first 2-3 sentences (best-effort) for the card TL;DR."""
        cleaned = self._text_processor.sanitize_summary_text(text) if text else ""
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""

        sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", cleaned) if s.strip()]
        compact = " ".join(sentences[:max_sentences]).strip() if sentences else cleaned

        return self._truncate_plain_text(compact, max_chars)

    def _build_compact_card_html(
        self, summary_shaped: dict[str, Any], llm: Any, chunks: int | None, *, reader: bool
    ) -> str:
        """Build a compact, scannable summary card in Telegram HTML format."""

        def capped(items: list[str], cap: int, *, sep: str) -> tuple[str, int]:
            clean = [str(x).strip() for x in items if str(x).strip()]
            shown = clean[:cap]
            hidden = max(0, len(clean) - len(shown))
            return (sep.join(shown), hidden) if shown else ("", 0)

        meta = summary_shaped.get("metadata") or {}
        title = str(meta.get("title") or "").strip() if isinstance(meta, dict) else ""
        canonical_url = ""
        domain = ""
        if isinstance(meta, dict):
            canonical_url = str(meta.get("canonical_url") or "").strip()
            domain = str(meta.get("domain") or "").strip()

        if not domain and canonical_url:
            domain = self._extract_domain_from_url(canonical_url) or ""

        reading_time = summary_shaped.get("estimated_reading_time_min")
        reading_time_str = ""
        try:
            if reading_time is not None:
                reading_time_val = int(reading_time)
                if reading_time_val > 0:
                    reading_time_str = f"~{reading_time_val} min"
        except Exception:
            reading_time_str = ""

        # Title (link) + source + reading time
        display_title = self._truncate_plain_text(title or domain or "Article", 180)
        if canonical_url:
            title_line = (
                f'<a href="{html.escape(canonical_url, quote=True)}">'
                f"{html.escape(display_title)}"
                "</a>"
            )
        else:
            title_line = html.escape(display_title)

        meta_parts: list[str] = []
        if domain:
            meta_parts.append(html.escape(domain))
        if reading_time_str:
            meta_parts.append(html.escape(reading_time_str))
        meta_line = " · ".join(meta_parts)

        # TL;DR (2-3 sentences)
        tldr_raw = str(summary_shaped.get("tldr") or "").strip()
        if not tldr_raw:
            tldr_raw = str(summary_shaped.get("summary_250") or "").strip()
        tldr_compact = self._compact_tldr(tldr_raw)

        # Key takeaways (max 5)
        takeaways = summary_shaped.get("key_ideas") or []
        if not isinstance(takeaways, list):
            takeaways = []
        takeaways_clean: list[str] = []
        for item in takeaways:
            s = str(item or "").strip()
            if not s:
                continue
            s = self._text_processor.sanitize_summary_text(s)
            s = self._truncate_plain_text(s, 180)
            takeaways_clean.append(html.escape(s))
            if len(takeaways_clean) >= 5:
                break

        # Key stats (top 3-5)
        key_stats = summary_shaped.get("key_stats") or []
        stats_lines: list[str] = []
        if isinstance(key_stats, list) and key_stats:
            stats_lines = self._data_formatter.format_key_stats_compact(key_stats[:5])

        # Trim & structure metadata (chat view)
        tags_raw = summary_shaped.get("topic_tags") or []
        tags: list[str] = tags_raw if isinstance(tags_raw, list) else []
        tags_shown, tags_hidden = capped(tags, 5, sep=" ")

        entities = summary_shaped.get("entities") or {}
        people: list[str] = []
        orgs: list[str] = []
        places: list[str] = []
        if isinstance(entities, dict):
            people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
            orgs = [str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()]
            places = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]

        people_shown, people_hidden = capped(people, 5, sep=", ")
        orgs_shown, orgs_hidden = capped(orgs, 5, sep=", ")
        places_shown, places_hidden = capped(places, 5, sep=", ")

        lines: list[str] = []
        lines.append(title_line)
        if meta_line:
            lines.append(f"<i>{meta_line}</i>")

        if tldr_compact:
            lines.extend(["", "<b>TL;DR</b>", html.escape(tldr_compact)])

        if takeaways_clean:
            lines.extend(["", "<b>Key takeaways</b>"])
            lines.extend([f"• {t}" for t in takeaways_clean])

        if stats_lines:
            lines.extend(["", "<b>Key stats</b>"])
            lines.extend(stats_lines[:5])

        meta_lines: list[str] = []
        if tags_shown:
            tag_tail = f" (+{tags_hidden})" if tags_hidden else ""
            meta_lines.append("Tags: " + html.escape(tags_shown + tag_tail))
        if people_shown:
            tail = f" (+{people_hidden})" if people_hidden else ""
            meta_lines.append("People: " + html.escape(people_shown + tail))
        if orgs_shown:
            tail = f" (+{orgs_hidden})" if orgs_hidden else ""
            meta_lines.append("Orgs: " + html.escape(orgs_shown + tail))
        if places_shown:
            tail = f" (+{places_hidden})" if places_hidden else ""
            meta_lines.append("Places: " + html.escape(places_shown + tail))

        if meta_lines:
            lines.extend(["", "<b>Metadata</b>"])
            lines.extend(meta_lines)

        # In DEBUG mode, append minimal model/method metadata.
        if not reader:
            method = f"Chunked ({chunks} parts)" if chunks else "Single-pass"
            model_name = getattr(llm, "model", None) or "unknown"
            lines.extend(
                ["", f"<i>Model: {html.escape(str(model_name))} · {html.escape(method)}</i>"]
            )

        return "\n".join(lines).strip() or "✅ Summary Ready"

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
        summary_id_str = str(summary_id)

        # Row 1: More + export options
        export_row = [
            {"text": "More", "callback_data": f"more:{summary_id_str}"},
            {"text": "PDF", "callback_data": f"export:{summary_id_str}:pdf"},
            {"text": "MD", "callback_data": f"export:{summary_id_str}:md"},
            {"text": "HTML", "callback_data": f"export:{summary_id_str}:html"},
        ]

        # Row 2: Actions
        action_row = [
            {"text": "Save", "callback_data": f"save:{summary_id_str}"},
            {"text": "Similar", "callback_data": f"similar:{summary_id_str}"},
        ]

        # Row 3: Feedback
        feedback_row = [
            {"text": "👍", "callback_data": f"rate:{summary_id_str}:1"},
            {"text": "👎", "callback_data": f"rate:{summary_id_str}:-1"},
        ]

        return [export_row, action_row, feedback_row]

    def _create_inline_keyboard(self, summary_id: int | str) -> Any:
        """Create an inline keyboard markup for post-summary actions."""
        try:
            from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

            summary_id_str = str(summary_id)

            # Create keyboard with multiple rows
            keyboard = [
                # Row 1: More + export options
                [
                    InlineKeyboardButton("More", callback_data=f"more:{summary_id_str}"),
                    InlineKeyboardButton("PDF", callback_data=f"export:{summary_id_str}:pdf"),
                    InlineKeyboardButton("MD", callback_data=f"export:{summary_id_str}:md"),
                    InlineKeyboardButton("HTML", callback_data=f"export:{summary_id_str}:html"),
                ],
                # Row 2: Actions
                [
                    InlineKeyboardButton("Save", callback_data=f"save:{summary_id_str}"),
                    InlineKeyboardButton("Similar", callback_data=f"similar:{summary_id_str}"),
                ],
                # Row 3: Feedback
                [
                    InlineKeyboardButton("👍", callback_data=f"rate:{summary_id_str}:1"),
                    InlineKeyboardButton("👎", callback_data=f"rate:{summary_id_str}:-1"),
                ],
            ]

            return InlineKeyboardMarkup(keyboard)
        except ImportError:
            logger.debug("pyrogram_not_available_for_action_buttons")
            return None
        except Exception as e:
            logger.warning("create_action_buttons_failed", extra={"error": str(e)})
            return None

    async def _send_action_buttons(self, message: Any, summary_id: int | str) -> None:
        """Send action buttons as a separate message after the summary."""
        try:
            keyboard = self._create_inline_keyboard(summary_id)
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
    ) -> None:
        """Send summary where each top-level JSON field is a separate message,
        then attach the full JSON as a .json document with a descriptive filename.

        Args:
            message: Telegram message object
            summary_shaped: Summary data dictionary
            llm: LLM instance (for model name)
            chunks: Number of chunks used (optional)
            summary_id: Database summary ID for action buttons (optional)
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
                    await self._progress_tracker.finalize(
                        message,
                        card_text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    job_card_finalized = True

                    if reader:
                        return
            except Exception as exc:
                raise_if_cancelled(exc)

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
                await self._send_action_buttons(message, summary_id)

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
                await self._send_action_buttons(message, summary_id)

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
            header = "Additional Research Highlights"

            reader = False
            if self._verbosity_resolver is not None:
                from app.core.verbosity import VerbosityLevel

                reader = (
                    await self._verbosity_resolver.get_verbosity(message)
                ) == VerbosityLevel.READER

            if correlation_id and not reader:
                header += f"\nCorrelation ID: {correlation_id}"
            await self._response_sender.safe_reply(message, header)

            sections_sent = False

            overview = insights.get("topic_overview")
            if isinstance(overview, str) and overview.strip():
                sections_sent = True
                await self._text_processor.send_long_text(
                    message,
                    "<b>🧭 Overview</b>\n"
                    + self._text_processor.sanitize_summary_text(overview.strip()),
                    parse_mode="HTML",
                )

            facts_section: list[str] = []
            facts = insights.get("new_facts")
            if isinstance(facts, list):
                for idx, fact in enumerate(facts[:5], start=1):
                    if not isinstance(fact, dict):
                        continue
                    fact_text = str(fact.get("fact", "")).strip()
                    if not fact_text:
                        continue
                    fact_lines = [f"{idx}. {self._text_processor.sanitize_summary_text(fact_text)}"]

                    why_matters = str(fact.get("why_it_matters", "")).strip()
                    if why_matters:
                        fact_lines.append(
                            f"   • Why it matters: {self._text_processor.sanitize_summary_text(why_matters)}"
                        )

                    source_hint = str(fact.get("source_hint", "")).strip()
                    if source_hint:
                        fact_lines.append(
                            f"   • Source hint: {self._text_processor.sanitize_summary_text(source_hint)}"
                        )

                    confidence = fact.get("confidence")
                    if confidence is not None:
                        try:
                            conf_val = float(confidence)
                            fact_lines.append(f"   • Confidence: {conf_val:.0%}")
                        except Exception:
                            fact_lines.append(
                                f"   • Confidence: {self._text_processor.sanitize_summary_text(str(confidence))}"
                            )

                    facts_section.append("\n".join(fact_lines))
            if facts_section:
                sections_sent = True
                await self._text_processor.send_long_text(
                    message,
                    "<b>📌 Fresh Facts</b>\n" + "\n\n".join(facts_section),
                    parse_mode="HTML",
                )

            def _clean_list(items: list[Any]) -> list[str]:
                cleaned: list[str] = []
                for item in items:
                    text = str(item).strip()
                    if not text:
                        continue
                    cleaned.append(self._text_processor.sanitize_summary_text(text))
                return cleaned

            open_questions = insights.get("open_questions")
            if isinstance(open_questions, list):
                questions = _clean_list(open_questions)[:5]
                if questions:
                    sections_sent = True
                    await self._text_processor.send_long_text(
                        message,
                        "<b>❓ Open Questions</b>\n" + "\n".join(f"- {q}" for q in questions),
                        parse_mode="HTML",
                    )

            suggested_sources = insights.get("suggested_sources")
            if isinstance(suggested_sources, list):
                sources = _clean_list(suggested_sources)[:5]
                if sources:
                    sections_sent = True
                    await self._text_processor.send_long_text(
                        message,
                        "<b>🔗 Suggested Follow-up</b>\n" + "\n".join(f"- {s}" for s in sources),
                        parse_mode="HTML",
                    )

            expansion = insights.get("expansion_topics")
            if isinstance(expansion, list):
                exp_clean = _clean_list(expansion)[:8]
                if exp_clean:
                    sections_sent = True
                    await self._text_processor.send_long_text(
                        message,
                        "<b>🧠 Expansion Topics</b> (beyond the article)\n"
                        + "\n".join(f"- {item}" for item in exp_clean),
                        parse_mode="HTML",
                    )

            next_steps = insights.get("next_exploration")
            if isinstance(next_steps, list):
                nxt_clean = _clean_list(next_steps)[:8]
                if nxt_clean:
                    sections_sent = True
                    await self._text_processor.send_long_text(
                        message,
                        "<b>🚀 What to explore next</b>\n"
                        + "\n".join(f"- {step}" for step in nxt_clean),
                        parse_mode="HTML",
                    )

            caution = insights.get("caution")
            if isinstance(caution, str) and caution.strip():
                sections_sent = True
                await self._text_processor.send_long_text(
                    message,
                    "<b>⚠️ Caveats</b>\n"
                    + self._text_processor.sanitize_summary_text(caution.strip()),
                    parse_mode="HTML",
                )

            if not sections_sent:
                await self._response_sender.safe_reply(
                    message, "No additional research insights were available."
                )

        except Exception as exc:  # pragma: no cover - defensive
            raise_if_cancelled(exc)
            logger.error("insights_message_error", extra={"error": str(exc)})

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
            # Clear progress tracker
            if self._progress_tracker is not None:
                self._progress_tracker.clear(message)

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
