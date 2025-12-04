import asyncio
import types
from unittest.mock import AsyncMock, MagicMock

from app.infrastructure.messaging.event_handlers import EmbeddingGenerationEventHandler
from app.services.note_text_builder import build_note_text


def test_sync_vector_store_embeds_note_text_and_user_notes():
    request_id = 123
    summary_id = 456
    payload = {
        "summary_250": "A short summary of the article.",
        "metadata": {
            "title": "Interesting Article",
            "user_note": "My personal note about this summary.",
            "tags": ["news"],
        },
    }

    summary = {
        "id": summary_id,
        "json_payload": payload,
        "lang": "en",
        "request": {"lang_detected": "en"},
    }

    db = types.SimpleNamespace(async_get_summary_by_request=AsyncMock(return_value=summary))
    embedding_service = MagicMock()
    embedding_service.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])

    generator = types.SimpleNamespace(db=db, embedding_service=embedding_service)

    vector_store = MagicMock()
    handler = EmbeddingGenerationEventHandler(generator, vector_store)

    expected_note_text = build_note_text(
        payload,
        request_id=request_id,
        summary_id=summary_id,
        language="en",
        user_note="My personal note about this summary.",
    ).text

    asyncio.run(handler._sync_vector_store(request_id))

    embedding_service.generate_embedding.assert_awaited_once_with(expected_note_text, language="en")

    vector_store.upsert_notes.assert_called_once()
    vectors, metadatas = vector_store.upsert_notes.call_args.args

    assert vectors == [[0.1, 0.2, 0.3]]
    assert metadatas[0]["text"] == expected_note_text
    assert metadatas[0]["request_id"] == request_id
    assert metadatas[0]["summary_id"] == summary_id
