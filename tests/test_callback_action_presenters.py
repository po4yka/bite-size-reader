from __future__ import annotations

from types import SimpleNamespace

from app.adapters.telegram.callback_action_presenters import CallbackActionPresenters
from app.core.ui_strings import t


def test_build_similar_query_prefers_title_and_tags() -> None:
    presenters = CallbackActionPresenters(lang="en")

    query = presenters.build_similar_query(
        {
            "metadata": {"title": "Example title"},
            "topic_tags": ["#ai", "#ml", "#ignored"],
            "key_ideas": ["Should not be used"],
        }
    )

    assert query == "Example title #ai #ml"


def test_build_similar_query_falls_back_to_first_key_idea() -> None:
    presenters = CallbackActionPresenters(lang="en")

    query = presenters.build_similar_query(
        {
            "metadata": {},
            "topic_tags": [],
            "key_ideas": ["Use this idea for search", "Ignore this"],
        }
    )

    assert query == "Use this idea for search"


def test_render_more_details_handles_html_and_truncation() -> None:
    presenters = CallbackActionPresenters(lang="en")

    text = presenters.render_more_details(
        {
            "metadata": {"title": "<Title>", "domain": "example.com<script>"},
            "summary_1000": "Long summary",
            "insights": {
                "topic_overview": "A" * 510,
                "new_facts": [{"fact": "<Fact>"}, {"fact": "B" * 230}],
            },
            "answered_questions": ["What happened?<tag>"],
            "topic_tags": ["#alpha", "#beta", "#gamma", "#delta", "#epsilon", "#zeta"],
            "entities": {
                "people": ["Alice"],
                "organizations": ["<Org>"],
                "locations": ["Tbilisi"],
            },
        }
    )

    assert "&lt;Title&gt;" in text
    assert "example.com&lt;script&gt;" in text
    assert t("more_long_summary", "en") in text
    assert t("more_research_highlights", "en") in text
    assert t("more_answered_questions", "en") in text
    assert t("more_tags", "en") in text
    assert t("more_entities", "en") in text
    assert "…" in text
    assert "(+1)" in text


def test_render_more_details_falls_back_when_payload_empty() -> None:
    presenters = CallbackActionPresenters(lang="en")

    text = presenters.render_more_details({"metadata": {}, "topic_tags": []})

    assert text == t("cb_no_details", "en")


def test_render_related_summary_includes_source_link() -> None:
    presenters = CallbackActionPresenters(lang="en")

    text = presenters.render_related_summary(
        {
            "title": "<A title>",
            "tldr": "Short <summary>",
            "key_ideas": ["Idea 1", "Idea 2"],
            "topic_tags": ["#x", "#y"],
            "url": "https://example.com/source",
        }
    )

    assert "&lt;A title&gt;" in text
    assert "Short &lt;summary&gt;" in text
    assert "Idea 1" in text
    assert "Source" in text


def test_format_digest_post_fallback_appends_original_link() -> None:
    presenters = CallbackActionPresenters(lang="en")

    text = presenters.format_digest_post_fallback(
        SimpleNamespace(text="Stored post", url="https://example.com/post"),
        "https://example.com/post",
    )

    assert text.startswith("**Full Post**")
    assert "Stored post" in text
    assert "Original" in text
