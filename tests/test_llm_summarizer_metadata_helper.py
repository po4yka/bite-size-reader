from app.adapters.content.llm_summarizer_metadata import LLMSummaryMetadataHelper


def test_extract_heading_title_prefers_youtube_title_header() -> None:
    content = (
        "[Source: YouTube video transcript. Treat this as spoken video content.]\n\n"
        "Title: Rust Ownership Deep Dive | Channel: Ferris TV | Duration: 10m 0s\n\n"
        "Transcript body starts here."
    )

    assert LLMSummaryMetadataHelper._extract_heading_title(content) == "Rust Ownership Deep Dive"


def test_extract_heading_title_skips_source_preamble_line() -> None:
    content = (
        "[Source: YouTube video transcript. Treat this as spoken video content.]\n\n"
        "Fallback Title Line\n\n"
        "Body text."
    )

    assert LLMSummaryMetadataHelper._extract_heading_title(content) == "Fallback Title Line"


def test_extract_heading_title_prefers_markdown_heading() -> None:
    content = "# Main Heading\n\nBody text."

    assert LLMSummaryMetadataHelper._extract_heading_title(content) == "Main Heading"


def test_extract_heading_title_skips_metadata_only_lines() -> None:
    content = (
        "[Source: YouTube video transcript.]\n\n"
        "Channel: Ferris TV\n"
        "Duration: 10m 0s\n"
        "Resolution: 1080p\n"
        "Clean fallback title\n"
    )

    assert LLMSummaryMetadataHelper._extract_heading_title(content) == "Clean fallback title"


def test_extract_heading_title_returns_none_when_no_suitable_line() -> None:
    content = (
        "[Source: YouTube video transcript.]\n\n"
        "Channel: Ferris TV\n"
        "Duration: 10m 0s\n"
        "Resolution: 1080p\n" + ("A" * 141) + "\n"
    )

    assert LLMSummaryMetadataHelper._extract_heading_title(content) is None
