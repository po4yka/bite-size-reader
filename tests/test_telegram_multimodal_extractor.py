from __future__ import annotations

from types import SimpleNamespace

from app.adapters.telegram.multimodal_extractor import (
    build_source_item_from_telegram_payload,
    build_telegram_normalized_document,
    build_telegram_summary_context,
    classify_telegram_messages_source_kind,
)
from app.domain.models.source import SourceKind


def _album_message(
    message_id: int, *, caption: str | None = None, file_id: str = "photo"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=message_id,
        message_id=message_id,
        text=None,
        caption=caption,
        chat=SimpleNamespace(id=-100777),
        media_group_id="album-1",
        photo=[SimpleNamespace(file_id=file_id, width=1280, height=720)],
        document=None,
        video=None,
        animation=None,
        forward_from_chat=SimpleNamespace(id=-10042, title="Source Channel"),
        forward_from_message_id=88,
        forward_from=None,
        forward_sender_name=None,
    )


def test_album_payload_builds_one_multimodal_source_item() -> None:
    payload = [
        _album_message(10, caption="Album caption", file_id="photo-1"),
        _album_message(11, file_id="photo-2"),
    ]

    source_item = build_source_item_from_telegram_payload(payload)

    assert classify_telegram_messages_source_kind(payload) == SourceKind.TELEGRAM_ALBUM
    assert source_item.kind == SourceKind.TELEGRAM_ALBUM
    assert source_item.telegram_media_group_id == "album-1"
    assert source_item.metadata["message_ids"] == [10, 11]


def test_album_payload_preserves_media_order_and_forward_provenance() -> None:
    payload = [
        _album_message(10, caption="Album caption", file_id="photo-1"),
        _album_message(11, file_id="photo-2"),
    ]
    source_item = build_source_item_from_telegram_payload(payload)

    document, metadata = build_telegram_normalized_document(payload, source_item=source_item)

    assert document.source_kind == SourceKind.TELEGRAM_ALBUM
    assert document.media[0].url == "telegram://file/photo-1"
    assert document.media[1].url == "telegram://file/photo-2"
    assert document.text == "Album caption"
    assert metadata["forward_from_chat_title"] == "Source Channel"
    assert metadata["message_ids"] == [10, 11]


def test_summary_context_includes_source_and_caption() -> None:
    payload = [
        _album_message(10, caption="Album caption", file_id="photo-1"),
        _album_message(11, file_id="photo-2"),
    ]

    summary_context = build_telegram_summary_context(payload)

    assert summary_context is not None
    assert "Forwarded from: Source Channel" in summary_context
    assert "Album caption" in summary_context


def test_video_payload_uses_shared_video_source_extractor() -> None:
    payload = SimpleNamespace(
        id=21,
        message_id=21,
        text=None,
        caption="Video caption",
        chat=SimpleNamespace(id=-100777),
        media_group_id=None,
        photo=None,
        document=None,
        video=SimpleNamespace(file_id="video-1", duration=42),
        animation=None,
        forward_from_chat=SimpleNamespace(id=-10042, title="Source Channel"),
        forward_from_message_id=88,
        forward_from=None,
        forward_sender_name=None,
    )

    source_item = build_source_item_from_telegram_payload(payload)
    document, metadata = build_telegram_normalized_document(payload, source_item=source_item)

    assert document.media[0].kind.value == "video"
    assert document.text == "Title: Source Channel\n\nVideo caption"
    assert metadata["video_processing_strategy"] == "shared_video_source_extractor"
    assert metadata["video_provenance"]["primary_fact_source"] == "body"
