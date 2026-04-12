from __future__ import annotations

from types import SimpleNamespace

from app.adapters.content.multi_source_classification import (
    build_source_item_from_submission,
    classify_telegram_message_source_kind,
    classify_url_source_kind,
)
from app.application.dto.aggregation import SourceSubmission
from app.domain.models.source import SourceKind


def test_classify_url_source_kind_detects_platforms() -> None:
    assert (
        classify_url_source_kind("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        == SourceKind.YOUTUBE_VIDEO
    )
    assert classify_url_source_kind("https://x.com/user/status/123") == SourceKind.X_POST
    assert classify_url_source_kind("https://x.com/i/article/456") == SourceKind.X_ARTICLE
    assert (
        classify_url_source_kind("https://www.threads.net/@user/post/abc")
        == SourceKind.THREADS_POST
    )
    assert (
        classify_url_source_kind("https://www.instagram.com/reel/abc123/")
        == SourceKind.INSTAGRAM_REEL
    )
    assert classify_url_source_kind("https://example.com/article") == SourceKind.WEB_ARTICLE


def test_classify_telegram_message_source_kind_prefers_album_then_media() -> None:
    album_message = SimpleNamespace(media_group_id="album-1", photo=[SimpleNamespace(file_id="p1")])
    media_message = SimpleNamespace(media_group_id=None, photo=[SimpleNamespace(file_id="p1")])
    text_message = SimpleNamespace(
        media_group_id=None, photo=None, document=None, video=None, animation=None
    )

    assert classify_telegram_message_source_kind(album_message) == SourceKind.TELEGRAM_ALBUM
    assert (
        classify_telegram_message_source_kind(media_message) == SourceKind.TELEGRAM_POST_WITH_IMAGES
    )
    assert classify_telegram_message_source_kind(text_message) == SourceKind.TELEGRAM_POST


def test_build_source_item_from_telegram_submission_uses_message_identity() -> None:
    message = SimpleNamespace(
        id=77,
        message_id=77,
        text=None,
        caption="Forwarded caption",
        chat=SimpleNamespace(id=-100123),
        media_group_id=None,
        photo=[SimpleNamespace(file_id="photo-1")],
        document=None,
        video=None,
        animation=None,
        forward_from_chat=SimpleNamespace(id=-1009, title="Source Channel"),
        forward_from=None,
        forward_sender_name=None,
    )

    source_item = build_source_item_from_submission(SourceSubmission.from_telegram_message(message))

    assert source_item.kind == SourceKind.TELEGRAM_POST_WITH_IMAGES
    assert source_item.telegram_chat_id == -100123
    assert source_item.telegram_message_id == 77
    assert source_item.title_hint == "Source Channel"
