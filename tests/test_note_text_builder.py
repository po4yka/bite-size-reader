from app.services.embedding_service import prepare_text_for_embedding
from app.services.note_text_builder import NoteText, build_note_text


def test_build_note_text_combines_summary_and_user_note():
    payload = {
        "summary_250": "Concise summary.",
        "summary_1000": "Extended summary text that provides more detail.",
        "tldr": "Short takeaway.",
        "key_ideas": ["idea one", "idea two"],
        "topic_tags": ["#ai", "#news"],
        "metadata": {"title": "Article title"},
    }

    user_note = "Personal note about the article."

    expected_summary_text = prepare_text_for_embedding(
        title="Article title",
        summary_1000="Extended summary text that provides more detail.",
        summary_250="Concise summary.",
        tldr="Short takeaway.",
        key_ideas=["idea one", "idea two"],
        topic_tags=["ai", "news"],
    )

    result = build_note_text(
        payload,
        request_id=1,
        summary_id=2,
        language="en",
        user_note=user_note,
    )

    assert isinstance(result, NoteText)
    assert result.text == f"{expected_summary_text} {user_note}"
    assert result.metadata == {
        "request_id": 1,
        "summary_id": 2,
        "language": "en",
        "tags": ["ai", "news"],
    }


def test_build_note_text_handles_missing_payload_with_user_note():
    result = build_note_text(
        None,
        request_id=None,
        summary_id=None,
        language=None,
        user_note="Standalone note",
    )

    assert result.text == "Standalone note"
    assert result.metadata == {
        "request_id": None,
        "summary_id": None,
        "language": None,
        "tags": [],
    }
