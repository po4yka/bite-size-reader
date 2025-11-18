import pytest

from app.core import html_utils


@pytest.fixture(autouse=True)
def _disable_optional_dependencies(monkeypatch):
    """Force html_utils helpers to exercise their lightweight fallbacks."""
    monkeypatch.setattr(html_utils, "_HAS_TRAFILATURA", False)
    monkeypatch.setattr(html_utils, "trafilatura", None)


def test_html_to_text_fallback_strips_scripts_and_formats_lists():
    html = (
        "<html><body>"
        "<script>bad()</script><style>.hidden{}</style>"
        "<h1>Title</h1><p>Paragraph</p><ul><li>Item</li><li>Second</li></ul>"
        "</body></html>"
    )

    text = html_utils.html_to_text(html)

    assert text == "Title\n\nParagraph\n\n- Item\n- Second"


def test_clean_markdown_article_text_removes_boilerplate_and_noise():
    markdown = (
        "```python\nprint('x')\n```\n"
        "Normal text with [link](https://example.com) and `inline`\n"
        "![alt](image.png)\n"
        "Share this article\n"
        "Another line.\n\n"
        "[ref]: http://foo\n"
    )

    cleaned = html_utils.clean_markdown_article_text(markdown)

    assert cleaned == "Normal text with link and\n\nAnother line."


def test_normalize_text_removes_urls_and_emails():
    noisy = "Email me at foo@example.com!! Visit https://example.com   now"

    normalized = html_utils.normalize_text(noisy)

    assert "example.com" not in normalized
    assert "foo@" not in normalized
    assert "  " not in normalized
    assert normalized == "Email me at Visit now"


def test_chunk_sentences_groups_sentences_under_limit():
    sentences = [
        "Sentence one.",
        "Sentence two is longer.",
        "",
        "   ",
        "Third.",
    ]

    chunks = html_utils.chunk_sentences(sentences, max_chars=25)

    assert chunks == ["Sentence one.", "Sentence two is longer.", "Third."]
    assert html_utils.chunk_sentences("not a list") == []
