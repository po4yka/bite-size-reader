from __future__ import annotations

from app.services.metadata_builder import MetadataBuilder


def test_extract_user_note_prefers_payload_fields_before_metadata() -> None:
    payload = {
        "note": "payload note",
        "metadata": {
            "user_note": "metadata note",
        },
    }

    assert MetadataBuilder.extract_user_note(payload) == "metadata note"
    assert (
        MetadataBuilder.extract_user_note({"metadata": {"notes": "fallback note"}})
        == "fallback note"
    )
    assert MetadataBuilder.extract_user_note(None) is None


def test_build_metadata_uses_request_and_metadata_fallbacks() -> None:
    payload = {
        "metadata": {
            "canonical_url": "https://example.com/post",
            "title": "Example title",
            "published": "2024-01-01",
        }
    }
    summary_row = {
        "id": 9,
        "request_id": 7,
        "lang": "en",
        "request": {
            "normalized_url": "https://fallback.example.com",
        },
    }

    metadata = MetadataBuilder.build_metadata(payload, summary_row, user_scope="public")

    assert metadata == {
        "url": "https://example.com/post",
        "title": "Example title",
        "published_at": "2024-01-01",
        "user_scope": "public",
        "request_id": 7,
        "summary_id": 9,
        "language": "en",
    }


def test_prepare_for_upsert_returns_empty_when_no_note_text_can_be_built() -> None:
    text, metadata = MetadataBuilder.prepare_for_upsert(
        request_id=1,
        summary_id=2,
        payload={},
        language="en",
        user_scope="public",
        environment="dev",
    )

    assert text == ""
    assert metadata == {}


def test_prepare_for_upsert_builds_validated_metadata() -> None:
    payload = {
        "summary_250": "Concise summary",
        "topic_tags": ["#ai", "#news"],
        "metadata": {
            "title": "Article title",
            "domain": "example.com",
            "user_note": "Reader note",
        },
    }

    text, metadata = MetadataBuilder.prepare_for_upsert(
        request_id=12,
        summary_id=34,
        payload=payload,
        language="en",
        user_scope="Public Scope",
        environment="Dev Env",
        user_id=56,
    )

    assert "Concise summary" in text
    assert "Reader note" in text
    assert metadata["request_id"] == 12
    assert metadata["summary_id"] == 34
    assert metadata["user_id"] == 56
    assert metadata["environment"] == "devenv"
    assert metadata["user_scope"] == "publicscope"
    assert metadata["tags"] == ["ai", "news"]
    assert metadata["title"] == "Article title"
    assert metadata["source"] == "example.com"


def test_prepare_chunk_windows_for_upsert_skips_invalid_chunks_and_builds_neighbors() -> None:
    payload = {
        "topic_tags": ["#tech"],
        "semantic_boosters": ["booster one", "booster two"],
        "query_expansion_keywords": ["alpha", "beta"],
        "semantic_chunks": [
            {
                "chunk_id": "chunk-a",
                "window_id": "window-a",
                "text": "Chunk A text",
                "local_summary": "Chunk A summary",
                "local_keywords": ["k1", "k2"],
                "section": "lead",
                "language": "en",
                "topics": ["tech"],
            },
            {
                "text": "",
            },
            {
                "chunk_id": "chunk-c",
                "text": "Chunk C text",
                "local_keywords": ["k3"],
                "section": "body",
                "language": "ru",
            },
        ],
    }

    windows = MetadataBuilder.prepare_chunk_windows_for_upsert(
        request_id=1,
        summary_id=2,
        payload=payload,
        language="en",
        user_scope="public",
        environment="dev",
        user_id=3,
    )

    assert len(windows) == 2

    first_text, first_metadata = windows[0]
    assert "Chunk A text" in first_text
    assert "Chunk A summary" in first_text
    assert first_metadata["chunk_id"] == "chunk-a"
    assert first_metadata["window_id"] == "window-a"
    assert first_metadata["neighbor_chunk_ids"] == ["2:1"]
    assert first_metadata["topics"] == ["tech"]
    assert first_metadata["semantic_boosters"] == ["booster one", "booster two"]

    second_text, second_metadata = windows[1]
    assert "Chunk C text" in second_text
    assert second_metadata["chunk_id"] == "chunk-c"
    assert second_metadata["language"] == "ru"
    assert second_metadata["topics"] == ["tech"]
    assert second_metadata["neighbor_chunk_ids"] == ["2:1"]
