# ruff: noqa: E501
from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Handles message formatting and replies to Telegram users."""

    def __init__(
        self,
        safe_reply_func: Callable[[Any, str], Awaitable[None]] | None = None,
        reply_json_func: Callable[[Any, dict], Awaitable[None]] | None = None,
    ) -> None:
        # Optional callbacks allow the TelegramBot compatibility layer to
        # intercept replies during unit tests without duplicating formatter
        # logic. The callbacks are expected to be awaitable and accept the
        # same arguments as ``safe_reply`` / ``reply_json`` respectively.
        self._safe_reply_func = safe_reply_func
        self._reply_json_func = reply_json_func

        # Telegram silently rejects messages above ~4096 characters.
        # Keep a safety margin to avoid hitting the hard limit.
        self.MAX_MESSAGE_CHARS = 3500

    async def send_help(self, message: Any) -> None:
        """Send help message to user."""
        help_text = (
            "Bite-Size Reader\n\n"
            "Commands:\n"
            "- /help — show this help.\n"
            "- /summarize <URL> — summarize a URL.\n"
            "- /summarize_all <URLs> — summarize multiple URLs from one message.\n\n"
            "Usage:\n"
            "- You can simply send a URL (or several URLs) or forward a channel post — commands are optional.\n"
            "- You can also send /summarize and then a URL in the next message.\n"
            "- Multiple links in one message are supported; I can confirm or use /summarize_all to process immediately.\n\n"
            "Features:\n"
            "- Enhanced structured JSON output with schema validation\n"
            "- Intelligent model fallbacks for better reliability\n"
            "- Automatic content optimization based on model capabilities\n"
            "- /dbinfo — quick database health snapshot"
        )
        await self.safe_reply(message, help_text)

    async def send_welcome(self, message: Any) -> None:
        """Send welcome message to user."""
        welcome = (
            "Welcome to Bite-Size Reader!\n\n"
            "What I do:\n"
            "- Summarize articles from URLs using Firecrawl + OpenRouter.\n"
            "- Summarize forwarded channel posts.\n"
            "- Generate structured JSON summaries with enhanced reliability.\n\n"
            "How to use:\n"
            "- Send a URL directly, or use /summarize <URL>.\n"
            "- You can also send /summarize and then the URL in the next message.\n"
            "- For forwarded posts, use /summarize_forward and then forward a channel post.\n"
            '- Multiple links in one message are supported: I will ask "Process N links?" or use /summarize_all to process immediately.\n'
            "- /dbinfo shares a quick snapshot of the internal database so you can monitor storage.\n\n"
            "Notes:\n"
            "- I reply with a strict JSON object using advanced schema validation.\n"
            "- Intelligent model selection and fallbacks ensure high success rates.\n"
            "- Errors include an Error ID you can reference in logs."
        )
        await self.safe_reply(message, welcome)

    async def send_db_overview(self, message: Any, overview: dict[str, object]) -> None:
        """Send an overview of the database state."""
        lines = ["📚 Database Overview"]

        path_display = overview.get("path_display") or overview.get("path")
        if isinstance(path_display, str) and path_display:
            lines.append(f"Path: `{path_display}`")

        size_bytes = overview.get("db_size_bytes")
        if isinstance(size_bytes, int) and size_bytes >= 0:
            pretty_size = self._format_bytes(size_bytes)
            lines.append(f"Size: {pretty_size} ({size_bytes:,} bytes)")

        table_counts = overview.get("tables")
        if isinstance(table_counts, dict) and table_counts:
            lines.append("")
            lines.append("Tables:")
            for name in sorted(table_counts):
                lines.append(f"- {name}: {table_counts[name]}")
            truncated = overview.get("tables_truncated")
            if isinstance(truncated, int) and truncated > 0:
                lines.append(f"- ...and {truncated} more (not displayed)")

        total_requests = overview.get("total_requests")
        total_summaries = overview.get("total_summaries")
        totals: list[str] = []
        if isinstance(total_requests, int):
            totals.append(f"Requests: {total_requests}")
        if isinstance(total_summaries, int):
            totals.append(f"Summaries: {total_summaries}")
        if totals:
            lines.append("")
            lines.append("Totals: " + ", ".join(totals))

        statuses = overview.get("requests_by_status")
        if isinstance(statuses, dict) and statuses:
            lines.append("")
            lines.append("Requests by status:")
            for status in sorted(statuses):
                label = status or "unknown"
                lines.append(f"- {label}: {statuses[status]}")

        last_request = overview.get("last_request_at")
        last_summary = overview.get("last_summary_at")
        last_audit = overview.get("last_audit_at")
        timeline_parts: list[str] = []
        if isinstance(last_request, str) and last_request:
            timeline_parts.append(f"Last request: {last_request}")
        if isinstance(last_summary, str) and last_summary:
            timeline_parts.append(f"Last summary: {last_summary}")
        if isinstance(last_audit, str) and last_audit:
            timeline_parts.append(f"Last audit log: {last_audit}")
        if timeline_parts:
            lines.append("")
            lines.extend(timeline_parts)

        errors = overview.get("errors")
        if isinstance(errors, list) and errors:
            lines.append("")
            lines.append("Warnings:")
            for err in errors[:5]:
                lines.append(f"- {err}")

        await self.safe_reply(message, "\n".join(lines))

    async def send_enhanced_summary_response(
        self, message: Any, summary_shaped: dict[str, Any], llm: Any, chunks: int | None = None
    ) -> None:
        """Send enhanced summary where each top-level JSON field is a separate message,
        then attach the full JSON as a .json document with a descriptive filename."""
        try:
            # Optional short header
            try:
                method = f"Chunked ({chunks} parts)" if chunks else "Single-pass"
                model_name = getattr(llm, "model", None)
                header = (
                    f"🎉 Summary Ready\n🧠 Model: {model_name or 'unknown'}\n🔧 Method: {method}"
                )
                await self.safe_reply(message, header)
            except Exception:
                pass

            # Combined first message: TL;DR, Tags, Entities, Reading Time, Key Stats, Readability, SEO
            combined_lines: list[str] = []

            tl_dr = str(summary_shaped.get("summary_250", "")).strip()
            if tl_dr:
                tl_dr_clean = self._sanitize_summary_text(tl_dr)
                combined_lines.extend(["📋 TL;DR:", tl_dr_clean, ""])

            tags = [
                str(t).strip() for t in (summary_shaped.get("topic_tags") or []) if str(t).strip()
            ]
            if tags:
                combined_lines.append("🏷️ Tags: " + " ".join(tags))
                combined_lines.append("")

            entities = summary_shaped.get("entities") or {}
            if isinstance(entities, dict):
                people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
                orgs = [
                    str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()
                ]
                locs = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]
                ent_parts: list[str] = []
                if people:
                    ent_parts.append("👤 " + ", ".join(people[:10]))
                if orgs:
                    ent_parts.append("🏢 " + ", ".join(orgs[:10]))
                if locs:
                    ent_parts.append("🌍 " + ", ".join(locs[:10]))
                if ent_parts:
                    combined_lines.append("🧭 Entities: " + " | ".join(ent_parts))
                    combined_lines.append("")

            reading_time = summary_shaped.get("estimated_reading_time_min")
            if reading_time:
                combined_lines.append(f"⏱️ Reading time: ~{reading_time} min")
                combined_lines.append("")

            key_stats = summary_shaped.get("key_stats") or []
            if isinstance(key_stats, list) and key_stats:
                ks_lines: list[str] = ["📈 Key Stats:"]
                for ks in key_stats[:10]:
                    if isinstance(ks, dict):
                        label = str(ks.get("label", "")).strip()
                        value = ks.get("value")
                        unit = str(ks.get("unit", "")).strip()
                        if label and value is not None:
                            ks_lines.append(f"• {label}: {value} {unit}".rstrip())
                if len(ks_lines) > 1:
                    combined_lines.extend(ks_lines)
                    combined_lines.append("")

            readability = summary_shaped.get("readability") or {}
            if isinstance(readability, dict):
                method = readability.get("method")
                score = readability.get("score")
                level = readability.get("level")
                details = [str(x) for x in (method, score, level) if x is not None]
                if details:
                    combined_lines.append("🧮 Readability: " + ", ".join(map(str, details)))
                    combined_lines.append("")

            seo = [
                str(x).strip() for x in (summary_shaped.get("seo_keywords") or []) if str(x).strip()
            ]
            if seo:
                combined_lines.append("🔎 SEO Keywords: " + ", ".join(seo[:20]))
                combined_lines.append("")

            # Metadata
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

            if combined_lines:
                # Remove trailing empty lines
                while combined_lines and not combined_lines[-1]:
                    combined_lines.pop()
                await self._send_long_text(message, "\n".join(combined_lines))

            # Send separated summary fields (summary_250, summary_500, summary_1000, ...)
            summary_fields = [
                k
                for k in summary_shaped.keys()
                if k.startswith("summary_") and k.split("_", 1)[1].isdigit()
            ]

            def _key_num(k: str) -> int:
                try:
                    return int(k.split("_", 1)[1])
                except Exception:
                    return 0

            for key in sorted(summary_fields, key=_key_num):
                content = str(summary_shaped.get(key, "")).strip()
                if content:
                    content = self._sanitize_summary_text(content)
                    await self._send_labelled_text(
                        message,
                        f"🧾 Summary {key.split('_', 1)[1]}",
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
                        await self._send_long_text(message, "💡 Key Ideas:\n" + "\n".join(chunk))
                        chunk = []
                if chunk:
                    await self._send_long_text(message, "💡 Key Ideas:\n" + "\n".join(chunk))

            # Send new field messages
            await self._send_new_field_messages(message, summary_shaped)

            # Finally attach full JSON as a document with a descriptive filename
            await self.reply_json(message, summary_shaped)

        except Exception:
            # Fallback to simpler format
            try:
                tl_dr = str(summary_shaped.get("summary_250", "")).strip()
                if tl_dr:
                    await self.safe_reply(message, f"📋 TL;DR:\n{tl_dr}")
            except Exception:
                pass

            await self.reply_json(message, summary_shaped)

    async def send_additional_insights_message(
        self, message: Any, insights: dict[str, Any], correlation_id: str | None = None
    ) -> None:
        """Send follow-up message summarizing additional research insights."""
        try:
            lines: list[str] = ["🔍 Additional Research Highlights"]

            if correlation_id:
                lines.append(f"🆔 Correlation ID: `{correlation_id}`")
                lines.append("")

            overview = insights.get("topic_overview")
            if isinstance(overview, str) and overview.strip():
                lines.append("🧭 Overview:")
                lines.append(self._sanitize_summary_text(overview.strip()))
                lines.append("")

            facts = insights.get("new_facts")
            if isinstance(facts, list) and facts:
                lines.append("📌 Fresh Facts:")
                for idx, fact in enumerate(facts[:5], start=1):
                    if not isinstance(fact, dict):
                        continue
                    fact_text = str(fact.get("fact", "")).strip()
                    if not fact_text:
                        continue
                    fact_line = f"{idx}. {self._sanitize_summary_text(fact_text)}"

                    why_matters = str(fact.get("why_it_matters", "")).strip()
                    if why_matters:
                        fact_line += (
                            f"\n   • Why it matters: {self._sanitize_summary_text(why_matters)}"
                        )

                    source_hint = str(fact.get("source_hint", "")).strip()
                    if source_hint:
                        fact_line += (
                            f"\n   • Source hint: {self._sanitize_summary_text(source_hint)}"
                        )

                    confidence = fact.get("confidence")
                    if confidence is not None:
                        try:
                            conf_val = float(confidence)
                            fact_line += f"\n   • Confidence: {conf_val:.0%}"
                        except Exception:
                            fact_line += (
                                f"\n   • Confidence: {self._sanitize_summary_text(str(confidence))}"
                            )

                    lines.append(fact_line)
                lines.append("")

            open_questions = insights.get("open_questions")
            if isinstance(open_questions, list):
                cleaned_questions = [
                    self._sanitize_summary_text(str(q).strip())
                    for q in open_questions
                    if str(q).strip()
                ]
                if cleaned_questions:
                    lines.append("❓ Open Questions:")
                    for question in cleaned_questions[:5]:
                        lines.append(f"- {question}")
                    lines.append("")

            suggested_sources = insights.get("suggested_sources")
            if isinstance(suggested_sources, list):
                cleaned_sources = [
                    self._sanitize_summary_text(str(src).strip())
                    for src in suggested_sources
                    if str(src).strip()
                ]
                if cleaned_sources:
                    lines.append("🔗 Suggested Follow-up:")
                    for src in cleaned_sources[:5]:
                        lines.append(f"- {src}")
                    lines.append("")

            # New: Expansion topics beyond the original text
            expansion = insights.get("expansion_topics")
            if isinstance(expansion, list):
                exp_clean = [
                    self._sanitize_summary_text(str(x).strip()) for x in expansion if str(x).strip()
                ]
                if exp_clean:
                    lines.append("🧠 Expansion Topics (beyond the article):")
                    for item in exp_clean[:8]:
                        lines.append(f"- {item}")
                    lines.append("")

            # New: What to explore next
            next_steps = insights.get("next_exploration")
            if isinstance(next_steps, list):
                nxt_clean = [
                    self._sanitize_summary_text(str(x).strip())
                    for x in next_steps
                    if str(x).strip()
                ]
                if nxt_clean:
                    lines.append("🚀 What to explore next:")
                    for step in nxt_clean[:8]:
                        lines.append(f"- {step}")
                    lines.append("")

            caution = insights.get("caution")
            if isinstance(caution, str) and caution.strip():
                lines.append("⚠️ Caveats:")
                lines.append(self._sanitize_summary_text(caution.strip()))
                lines.append("")

            while lines and not lines[-1].strip():
                lines.pop()

            if len(lines) == 1:
                lines.append("No additional research insights were available.")

            await self.safe_reply(message, "\n".join(lines))
        except Exception:
            pass

    async def send_custom_article(self, message: Any, article: dict[str, Any]) -> None:
        """Send the custom generated article with a nice header and downloadable JSON."""
        try:
            title = str(article.get("title", "")).strip() or "Custom Article"
            subtitle = str(article.get("subtitle", "") or "").strip()
            body = str(article.get("article_markdown", "")).strip()
            highlights = [
                str(x).strip() for x in (article.get("highlights") or []) if str(x).strip()
            ]

            header = f"📝 {title}"
            if subtitle:
                header += f"\n_{subtitle}_"
            await self.safe_reply(message, header, parse_mode="Markdown")

            if body:
                await self._send_long_text(message, body)

            if highlights:
                await self._send_long_text(
                    message, "⭐ Key Highlights:\n" + "\n".join([f"• {h}" for h in highlights[:10]])
                )

            await self.reply_json(message, article)
        except Exception:
            pass

    async def send_forward_summary_response(
        self, message: Any, forward_shaped: dict[str, Any]
    ) -> None:
        """Send forward summary with per-field messages, then attach full JSON file."""
        try:
            await self.safe_reply(message, "🎉 Forward Summary Ready")

            combined_lines: list[str] = []
            tl_dr = str(forward_shaped.get("summary_250", "")).strip()
            if tl_dr:
                tl_dr_clean = self._sanitize_summary_text(tl_dr)
                combined_lines.extend(["📋 TL;DR:", tl_dr_clean, ""])

            tags = [
                str(t).strip() for t in (forward_shaped.get("topic_tags") or []) if str(t).strip()
            ]
            if tags:
                combined_lines.append("🏷️ Tags: " + " ".join(tags))
                combined_lines.append("")

            entities = forward_shaped.get("entities") or {}
            if isinstance(entities, dict):
                people = [str(x).strip() for x in (entities.get("people") or []) if str(x).strip()]
                orgs = [
                    str(x).strip() for x in (entities.get("organizations") or []) if str(x).strip()
                ]
                locs = [str(x).strip() for x in (entities.get("locations") or []) if str(x).strip()]
                ent_parts: list[str] = []
                if people:
                    ent_parts.append("👤 " + ", ".join(people[:10]))
                if orgs:
                    ent_parts.append("🏢 " + ", ".join(orgs[:10]))
                if locs:
                    ent_parts.append("🌍 " + ", ".join(locs[:10]))
                if ent_parts:
                    combined_lines.append("🧭 Entities: " + " | ".join(ent_parts))
                    combined_lines.append("")

            reading_time = forward_shaped.get("estimated_reading_time_min")
            if reading_time:
                combined_lines.append(f"⏱️ Reading time: ~{reading_time} min")
                combined_lines.append("")

            key_stats = forward_shaped.get("key_stats") or []
            if isinstance(key_stats, list) and key_stats:
                ks_lines: list[str] = ["📈 Key Stats:"]
                for ks in key_stats[:10]:
                    if isinstance(ks, dict):
                        label = str(ks.get("label", "")).strip()
                        value = ks.get("value")
                        unit = str(ks.get("unit", "")).strip()
                        if label and value is not None:
                            ks_lines.append(f"• {label}: {value} {unit}".rstrip())
                if len(ks_lines) > 1:
                    combined_lines.extend(ks_lines)
                    combined_lines.append("")

            readability = forward_shaped.get("readability") or {}
            if isinstance(readability, dict):
                method = readability.get("method")
                score = readability.get("score")
                level = readability.get("level")
                details = [str(x) for x in (method, score, level) if x is not None]
                if details:
                    combined_lines.append("🧮 Readability: " + ", ".join(map(str, details)))
                    combined_lines.append("")

            seo = [
                str(x).strip() for x in (forward_shaped.get("seo_keywords") or []) if str(x).strip()
            ]
            if seo:
                combined_lines.append("🔎 SEO Keywords: " + ", ".join(seo[:20]))
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
                await self._send_long_text(message, "\n".join(combined_lines))

            # Separated summary fields
            summary_fields = [
                k
                for k in forward_shaped.keys()
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
                    content = self._sanitize_summary_text(content)
                    await self._send_labelled_text(
                        message,
                        f"🧾 Summary {key.split('_', 1)[1]}",
                        content,
                    )

            ideas = [
                str(x).strip() for x in (forward_shaped.get("key_ideas") or []) if str(x).strip()
            ]
            if ideas:
                await self._send_long_text(
                    message, "💡 Key Ideas:\n" + "\n".join([f"• {i}" for i in ideas])
                )

            # Send new field messages for forwards
            await self._send_new_field_messages(message, forward_shaped)
        except Exception:
            pass

        await self.reply_json(message, forward_shaped)

    async def reply_json(self, message: Any, obj: dict) -> None:
        """Reply with JSON object, using file upload for large content."""
        if self._reply_json_func is not None:
            await self._reply_json_func(message, obj)
            return

        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        # Prefer sending as a document always to avoid size limits
        try:
            bio = io.BytesIO(pretty.encode("utf-8"))
            bio.name = self._build_json_filename(obj)
            msg_any: Any = message
            await msg_any.reply_document(bio, caption="📊 Full Summary JSON attached")
            return
        except Exception as e:  # noqa: BLE001
            logger.error("reply_document_failed", extra={"error": str(e)})
        await self.safe_reply(message, f"```json\n{pretty}\n```")

    async def safe_reply(self, message: Any, text: str, *, parse_mode: str | None = None) -> None:
        """Safely reply to a message with error handling."""
        if self._safe_reply_func is not None:
            kwargs = {"parse_mode": parse_mode} if parse_mode is not None else {}
            await self._safe_reply_func(message, text, **kwargs)
            return

        try:
            msg_any: Any = message
            if parse_mode:
                await msg_any.reply_text(text, parse_mode=parse_mode)
            else:
                await msg_any.reply_text(text)
            try:
                logger.debug("reply_text_sent", extra={"length": len(text)})
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.error("reply_failed", extra={"error": str(e)})

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str
    ) -> None:
        """Send URL accepted notification."""
        try:
            from urllib.parse import urlparse

            url_domain = urlparse(norm).netloc if norm else "unknown"
            await self.safe_reply(
                message,
                f"✅ **Request Accepted**\n"
                f"🌐 Domain: `{url_domain}`\n"
                f"🔗 URL: `{norm[:60]}{'...' if len(norm) > 60 else ''}`\n"
                f"📋 Status: Fetching content...\n"
                f"🤖 Enhanced: Structured output with smart fallbacks",
            )
        except Exception:
            pass

    def _slugify(self, text: str, *, max_len: int = 60) -> str:
        """Create a filesystem-friendly slug from text."""
        text = text.strip().lower()
        # Replace non-word characters with hyphens
        text = re.sub(r"[^\w\-\s]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        if len(text) > max_len:
            text = text[:max_len].rstrip("-")
        return text or "summary"

    async def _send_long_text(self, message: Any, text: str) -> None:
        """Send text, splitting into multiple messages if too long for Telegram."""
        for chunk in self._chunk_text(text, max_len=self.MAX_MESSAGE_CHARS):
            if chunk:
                await self.safe_reply(message, chunk)

    async def _send_labelled_text(self, message: Any, label: str, body: str) -> None:
        """Send labelled text, splitting into continuation messages when needed."""
        body = body.strip()
        if not body:
            return
        label_clean = label.rstrip(":")
        primary_title = f"{label_clean}:"
        chunk_limit = max(200, self.MAX_MESSAGE_CHARS - len(primary_title) - 20)
        chunks = self._chunk_text(body, max_len=chunk_limit)
        if not chunks:
            return

        await self.safe_reply(message, f"{primary_title}\n{chunks[0]}")
        for idx, chunk in enumerate(chunks[1:], start=2):
            continuation_title = f"{label_clean} (cont. {idx}):"
            await self.safe_reply(message, f"{continuation_title}\n{chunk}")

    def _build_json_filename(self, obj: dict) -> str:
        """Build a descriptive filename for the JSON attachment."""
        # Prefer SEO keywords; fallback to first words of TL;DR
        seo = obj.get("seo_keywords") or []
        base: str | None = None
        if isinstance(seo, list) and seo:
            base = "-".join(self._slugify(str(x)) for x in seo[:3] if str(x).strip())
        if not base:
            tl = str(obj.get("summary_250", "")).strip()
            if tl:
                # Use first 6 words
                words = re.findall(r"\w+", tl)[:6]
                base = self._slugify("-".join(words))
        if not base:
            base = "summary"
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        return f"{base}-{timestamp}.json"

    def _format_bytes(self, size: int) -> str:
        """Convert byte count into a human-readable string."""
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} TB"

    def _chunk_text(self, text: str, *, max_len: int) -> list[str]:
        """Split text into chunks respecting Telegram's message length limit."""
        text = text.strip()
        if not text:
            return []

        chunks: list[str] = []
        remaining = text
        while len(remaining) > max_len:
            split_idx = self._find_split_index(remaining, max_len)
            chunk = remaining[:split_idx].rstrip("\n")
            if not chunk:
                chunk = remaining[:max_len]
                split_idx = max_len
            chunks.append(chunk)
            remaining = remaining[split_idx:]
            remaining = remaining.lstrip(" \n\r")
        if remaining:
            chunks.append(remaining)
        return chunks

    def _find_split_index(self, text: str, limit: int) -> int:
        """Find a sensible split index before the limit."""
        min_split = max(20, limit // 4)
        delimiters = [
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            "; ",
            ": ",
            ", ",
            " ",
        ]
        for delim in delimiters:
            idx = text.rfind(delim, 0, limit)
            if idx >= min_split:
                return min(limit, idx + len(delim))
        return limit

    def _sanitize_summary_text(self, text: str) -> str:
        """Normalize and clean summary text for safe sending.

        - Normalize to NFC
        - Remove control characters
        - Drop trailing isolated CJK run (1-3 chars) that looks like a stray token
        """
        try:
            s = unicodedata.normalize("NFC", text)
        except Exception:
            s = text
        # Remove control and non-printable chars
        s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")

        # If string ends with 1-3 CJK chars and preceding 15 chars have no CJK, drop the tail
        tail_match = re.search(r"([\u4E00-\u9FFF]{1,3})$", s)
        if tail_match:
            start = max(0, len(s) - 20)
            window = s[start : len(s) - len(tail_match.group(1))]
            if not re.search(r"[\u4E00-\u9FFF]", window):
                s = s[: -len(tail_match.group(1))].rstrip("-—")

        s = s.strip()

        if s and s[-1] not in ".!?…":
            last_sentence_end = max(s.rfind("."), s.rfind("!"), s.rfind("?"), s.rfind("…"))
            if last_sentence_end != -1 and last_sentence_end >= len(s) // 3:
                s = s[: last_sentence_end + 1].rstrip()
            else:
                s = s.rstrip("-—")
                if s and s[-1] not in ".!?…":
                    s = s + "."

        return s

    async def _send_new_field_messages(self, message: Any, shaped: dict[str, Any]) -> None:
        """Send messages for new fields like extractive quotes, highlights, etc."""
        try:
            # Extractive quotes
            quotes = shaped.get("extractive_quotes") or []
            if isinstance(quotes, list) and quotes:
                quote_lines = ["💬 Key Quotes:"]
                for i, quote in enumerate(quotes[:5], 1):
                    if isinstance(quote, dict) and quote.get("text"):
                        text = str(quote["text"]).strip()
                        if text:
                            quote_lines.append(f'{i}. "{text}"')
                if len(quote_lines) > 1:
                    await self._send_long_text(message, "\n".join(quote_lines))

            # Highlights
            highlights = [
                str(h).strip() for h in (shaped.get("highlights") or []) if str(h).strip()
            ]
            if highlights:
                await self._send_long_text(
                    message, "✨ Highlights:\n" + "\n".join([f"• {h}" for h in highlights[:10]])
                )

            # Questions answered (as Q&A pairs)
            questions_answered = shaped.get("questions_answered") or []
            if isinstance(questions_answered, list) and questions_answered:
                qa_lines = ["❓ Questions Answered:"]
                for i, qa in enumerate(questions_answered[:10], 1):
                    if isinstance(qa, dict):
                        question = str(qa.get("question", "")).strip()
                        answer = str(qa.get("answer", "")).strip()
                        if question:
                            qa_lines.append(f"\n{i}. **Q:** {question}")
                            if answer:
                                qa_lines.append(f"   **A:** {answer}")
                            else:
                                qa_lines.append("   **A:** _(No answer provided)_")
                if len(qa_lines) > 1:
                    await self._send_long_text(message, "\n".join(qa_lines))

            # Key points to remember
            key_points = [
                str(kp).strip()
                for kp in (shaped.get("key_points_to_remember") or [])
                if str(kp).strip()
            ]
            if key_points:
                await self._send_long_text(
                    message,
                    "🎯 Key Points to Remember:\n"
                    + "\n".join([f"• {kp}" for kp in key_points[:10]]),
                )

            # Topic taxonomy (if present and not empty)
            taxonomy = shaped.get("topic_taxonomy") or []
            if isinstance(taxonomy, list) and taxonomy:
                tax_lines = ["🏷️ Topic Classification:"]
                for tax in taxonomy[:5]:
                    if isinstance(tax, dict) and tax.get("label"):
                        label = str(tax["label"]).strip()
                        score = tax.get("score", 0.0)
                        if isinstance(score, int | float) and score > 0:
                            tax_lines.append(f"• {label} ({score:.1%})")
                        else:
                            tax_lines.append(f"• {label}")
                if len(tax_lines) > 1:
                    await self._send_long_text(message, "\n".join(tax_lines))

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
                    await self._send_long_text(message, "📤 Forward Info:\n" + "\n".join(fwd_parts))

        except Exception:
            pass

    async def send_firecrawl_start_notification(self, message: Any) -> None:
        """Send Firecrawl start notification."""
        try:
            await self.safe_reply(
                message,
                "🕷️ **Firecrawl Extraction**\n"
                "📡 Connecting to Firecrawl API...\n"
                "⏱️ This may take 10-30 seconds\n"
                "🔄 Enhanced processing pipeline active",
            )
        except Exception:
            pass

    async def send_firecrawl_success_notification(
        self, message: Any, excerpt_len: int, latency_sec: float
    ) -> None:
        """Send Firecrawl success notification."""
        try:
            await self.safe_reply(
                message,
                f"✅ **Content Extracted Successfully**\n"
                f"📊 Size: ~{excerpt_len:,} characters\n"
                f"⏱️ Extraction time: {latency_sec:.1f}s\n"
                f"🔄 Status: Preparing for enhanced AI analysis...",
            )
        except Exception:
            pass

    async def send_content_reuse_notification(self, message: Any) -> None:
        """Send content reuse notification."""
        try:
            await self.safe_reply(
                message,
                "♻️ **Reusing Cached Content**\n"
                "📊 Status: Content already extracted\n"
                "⚡ Proceeding to enhanced AI analysis...",
            )
        except Exception:
            pass

    async def send_cached_summary_notification(self, message: Any) -> None:
        """Inform the user that a cached summary is being reused."""
        try:
            await self.safe_reply(
                message,
                "♻️ **Using Cached Summary**\n⚡ Delivered instantly without extra processing",
            )
        except Exception:
            pass

    async def send_html_fallback_notification(self, message: Any, content_len: int) -> None:
        """Send HTML fallback notification."""
        try:
            await self.safe_reply(
                message,
                f"🔄 **Content Processing Update**\n"
                f"📄 Markdown extraction was empty\n"
                f"🛠️ Using HTML content extraction\n"
                f"📊 Processing {content_len:,} characters...\n"
                f"🤖 Enhanced pipeline will optimize for best results",
            )
        except Exception:
            pass

    async def send_language_detection_notification(
        self, message: Any, detected: str | None, content_preview: str
    ) -> None:
        """Send language detection notification."""
        try:
            await self.safe_reply(
                message,
                f"🌍 **Language Detection**\n"
                f"📝 Detected: `{detected or 'unknown'}`\n"
                f"📄 Content preview:\n"
                f"```\n{content_preview}\n```\n"
                f"🤖 Status: Preparing enhanced AI analysis with structured outputs...",
            )
        except Exception:
            pass

    async def send_content_analysis_notification(
        self,
        message: Any,
        content_len: int,
        max_chars: int,
        enable_chunking: bool,
        chunks: list[str] | None,
        structured_output_mode: str,
    ) -> None:
        """Send content analysis notification."""
        try:
            if enable_chunking and content_len > max_chars and (chunks or []):
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters\n"
                    f"🔀 Processing: Chunked analysis ({len(chunks or [])} chunks)\n"
                    f"🤖 Method: Advanced structured output with schema validation\n"
                    f"⚡ Status: Sending to AI model with smart fallbacks...",
                )
            elif not enable_chunking and content_len > max_chars:
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters (exceeds {max_chars:,} adaptive threshold)\n"
                    f"🔀 Processing: Single-pass (chunking disabled)\n"
                    f"🤖 Method: Enhanced structured output with intelligent fallbacks\n"
                    f"⚡ Status: Sending to AI model...",
                )
            else:
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters\n"
                    f"🔀 Processing: Single-pass summary\n"
                    f"🤖 Method: Structured output with schema validation\n"
                    f"⚡ Status: Sending to AI model...",
                )
        except Exception:
            pass

    async def send_llm_start_notification(
        self, message: Any, model: str, content_len: int, structured_output_mode: str
    ) -> None:
        """Send LLM start notification."""
        try:
            await self.safe_reply(
                message,
                f"🤖 **Enhanced AI Analysis Starting**\n"
                f"🧠 Model: `{model}`\n"
                f"📊 Content: {content_len:,} characters\n"
                f"🔧 Mode: {structured_output_mode.upper()} with smart fallbacks\n"
                f"⏱️ This may take 30-60 seconds...",
            )
        except Exception:
            pass

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str
    ) -> None:
        """Send LLM completion notification."""
        try:
            model_name = llm.model or "unknown"
            latency_sec = (llm.latency_ms or 0) / 1000.0

            if llm.status == "ok":
                # Success message with enhanced details
                tokens_used = (llm.tokens_prompt or 0) + (llm.tokens_completion or 0)
                cost_info = f" (${llm.cost_usd:.4f})" if llm.cost_usd else ""
                structured_info = ""
                if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                    mode = getattr(llm, "structured_output_mode", "unknown")
                    structured_info = f"\n🔧 Structured Output: {mode.upper()}"

                await self.safe_reply(
                    message,
                    f"🤖 **Enhanced AI Analysis Complete**\n"
                    f"✅ Status: Success\n"
                    f"🧠 Model: `{model_name}`\n"
                    f"⏱️ Processing time: {latency_sec:.1f}s\n"
                    f"🔢 Tokens used: {tokens_used:,}{cost_info}{structured_info}\n"
                    f"📋 Status: Generating enhanced summary...",
                )
            else:
                # Enhanced error message
                await self.safe_reply(
                    message,
                    f"🤖 **Enhanced AI Analysis Failed**\n"
                    f"❌ Status: Error\n"
                    f"🧠 Model: `{model_name}`\n"
                    f"⏱️ Processing time: {latency_sec:.1f}s\n"
                    f"🚨 Error: {llm.error_text or 'Unknown error'}\n"
                    f"🔄 Smart fallbacks: Active\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
        except Exception:
            pass

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        """Send forward request accepted notification."""
        try:
            await self.safe_reply(
                message,
                "✅ **Forward Request Accepted**\n"
                f"📺 Channel: {title}\n"
                "🤖 Enhanced processing with structured outputs...\n"
                "📋 Status: Generating summary...",
            )
        except Exception:
            pass

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        """Send forward language detection notification."""
        try:
            await self.safe_reply(
                message,
                f"🌍 **Language Detection**\n"
                f"📝 Detected: `{detected or 'unknown'}`\n"
                f"🤖 Processing with enhanced structured outputs...\n"
                f"⚡ Status: Sending to AI model...",
            )
        except Exception:
            pass

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        """Send forward completion notification."""
        try:
            status_emoji = "✅" if llm.status == "ok" else "❌"
            latency_sec = (llm.latency_ms or 0) / 1000.0
            structured_info = ""
            if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                mode = getattr(llm, "structured_output_mode", "unknown")
                structured_info = f"\n🔧 Schema: {mode.upper()}"

            await self.safe_reply(
                message,
                f"🤖 **Enhanced AI Analysis Complete**\n"
                f"{status_emoji} Status: {'Success' if llm.status == 'ok' else 'Error'}\n"
                f"⏱️ Time: {latency_sec:.1f}s{structured_info}\n"
                f"📋 Status: {'Generating summary...' if llm.status == 'ok' else 'Processing error...'}",
            )
        except Exception:
            pass

    async def send_error_notification(
        self, message: Any, error_type: str, correlation_id: str, details: str | None = None
    ) -> None:
        """Send error notification with enhanced formatting."""
        try:
            if error_type == "firecrawl_error":
                await self.safe_reply(
                    message,
                    f"❌ **Content Extraction Failed**\n"
                    f"🚨 Unable to extract readable content\n"
                    f"🆔 Error ID: `{correlation_id}`\n\n"
                    f"💡 **Possible Solutions:**\n"
                    f"• Try a different URL\n"
                    f"• Check if content is publicly accessible\n"
                    f"• Ensure URL points to text-based content",
                )
            elif error_type == "empty_content":
                await self.safe_reply(
                    message,
                    f"❌ **Content Extraction Failed**\n\n"
                    f"🚨 **Possible Causes:**\n"
                    f"• Website blocking automated access\n"
                    f"• Content behind paywall/login\n"
                    f"• Non-text content (images, videos)\n"
                    f"• Temporary server issues\n"
                    f"• Invalid or inaccessible URL\n\n"
                    f"💡 **Suggestions:**\n"
                    f"• Try a different URL\n"
                    f"• Check if content is publicly accessible\n"
                    f"• Ensure URL points to text-based content\n\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
            elif error_type == "processing_failed":
                detail_block = f"\n🔍 Reason: {details}" if details else ""
                if self._safe_reply_func is not None:
                    await self._safe_reply_func(
                        message,
                        f"Invalid summary format. Error ID: {correlation_id}{detail_block}",
                    )
                else:
                    await self.safe_reply(
                        message,
                        f"❌ **Enhanced Processing Failed**\n"
                        f"🚨 Invalid summary format despite smart fallbacks{detail_block}\n"
                        f"🆔 Error ID: `{correlation_id}`",
                    )
            elif error_type == "llm_error":
                detail_block = f"\n🔍 Provider response: {details}" if details else ""
                await self.safe_reply(
                    message,
                    f"❌ **Enhanced Processing Failed**\n"
                    f"🚨 LLM error despite smart fallbacks{detail_block}\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
            else:
                # Generic error
                await self.safe_reply(
                    message,
                    f"❌ **Error Occurred**\n"
                    f"🚨 {details or 'Unknown error'}\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
        except Exception:
            pass
