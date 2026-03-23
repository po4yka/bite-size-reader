"""Pure formatting helpers for Telegram callback actions."""

from __future__ import annotations

import html
from typing import Any, TypedDict, cast

from app.core.ui_strings import t


class _Insights(TypedDict, total=False):
    topic_overview: str
    new_facts: list[dict[str, Any]]


class CallbackActionPresenters:
    """Build callback action text and derived query strings."""

    def __init__(self, lang: str = "en") -> None:
        self._lang = lang

    def build_similar_query(self, summary_data: dict[str, Any]) -> str:
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

        return " ".join(query_parts).strip()

    def render_more_details(self, summary_data: dict[str, Any]) -> str:
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

        return "\n".join(lines).strip() or t("cb_no_details", self._lang)

    def render_related_summary(self, summary_data: dict[str, Any]) -> str:
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
            lines.append(f"\n{html.escape(', '.join(str(tag) for tag in tags[:6]))}")
        if url:
            lines.append(f'\n<a href="{html.escape(url)}">Source</a>')

        text = "\n".join(lines).strip()
        return text or t("cb_no_details", self._lang)

    def format_digest_post_fallback(self, post: Any, post_url: str) -> str:
        text_preview = post.text[:4000]
        reply_text = f"**Full Post**\n\n{text_preview}"
        if post_url:
            reply_text += f"\n\n[Original]({post_url})"
        return reply_text
