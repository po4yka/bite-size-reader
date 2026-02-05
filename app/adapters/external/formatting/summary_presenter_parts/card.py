"""Compact summary card rendering (Telegram HTML)."""

from __future__ import annotations

import html
import re
from typing import Any


def truncate_plain_text(text: str, max_len: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if max_len <= 0 or len(text) <= max_len:
        return text

    soft_min = max(0, int(max_len * 0.7))
    cut = text.rfind(" ", soft_min, max_len)
    if cut == -1:
        cut = max_len
    return text[:cut].rstrip() + "…"


def extract_domain_from_url(url: str) -> str | None:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = (parsed.netloc or "").strip()
        return host or None
    except Exception:
        return None


def compact_tldr(
    text: str,
    *,
    text_processor: Any,
    max_sentences: int = 3,
    max_chars: int = 520,
) -> str:
    cleaned = text_processor.sanitize_summary_text(text) if text else ""
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", cleaned) if s.strip()]
    compact = " ".join(sentences[:max_sentences]).strip() if sentences else cleaned
    return truncate_plain_text(compact, max_chars)


def build_compact_card_html(
    summary_shaped: dict[str, Any],
    llm: Any,
    chunks: int | None,
    *,
    reader: bool,
    text_processor: Any,
    data_formatter: Any,
) -> str:
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
        domain = extract_domain_from_url(canonical_url) or ""

    reading_time = summary_shaped.get("estimated_reading_time_min")
    reading_time_str = ""
    try:
        if reading_time is not None:
            reading_time_val = int(reading_time)
            if reading_time_val > 0:
                reading_time_str = f"~{reading_time_val} min"
    except Exception:
        reading_time_str = ""

    display_title = truncate_plain_text(title or domain or "Article", 180)
    if canonical_url:
        title_line = (
            f'<a href="{html.escape(canonical_url, quote=True)}">{html.escape(display_title)}</a>'
        )
    else:
        title_line = html.escape(display_title)

    meta_parts: list[str] = []
    if domain:
        meta_parts.append(html.escape(domain))
    if reading_time_str:
        meta_parts.append(html.escape(reading_time_str))
    meta_line = " · ".join(meta_parts)

    tldr_raw = (
        str(summary_shaped.get("tldr") or "").strip()
        or str(summary_shaped.get("summary_250") or "").strip()
    )
    tldr_compact = compact_tldr(tldr_raw, text_processor=text_processor)

    takeaways = summary_shaped.get("key_ideas") or []
    if not isinstance(takeaways, list):
        takeaways = []
    takeaways_clean: list[str] = []
    for item in takeaways:
        s = str(item or "").strip()
        if not s:
            continue
        s = text_processor.sanitize_summary_text(s)
        s = truncate_plain_text(s, 180)
        takeaways_clean.append(html.escape(s))
        if len(takeaways_clean) >= 5:
            break

    key_stats = summary_shaped.get("key_stats") or []
    stats_lines: list[str] = []
    if isinstance(key_stats, list) and key_stats:
        stats_lines = data_formatter.format_key_stats_compact(key_stats[:5])

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

    lines: list[str] = [title_line]
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

    if not reader:
        method = f"Chunked ({chunks} parts)" if chunks else "Single-pass"
        model_name = getattr(llm, "model", None) or "unknown"
        lines.extend(["", f"<i>Model: {html.escape(str(model_name))} · {html.escape(method)}</i>"])

    return "\n".join(lines).strip() or "✅ Summary Ready"
