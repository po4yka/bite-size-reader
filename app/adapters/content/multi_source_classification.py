"""Source classification helpers for mixed-source aggregation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.application.dto.aggregation import SourceSubmission, SourceSubmissionKind
from app.core.url_utils import normalize_url
from app.core.urls.twitter import is_twitter_article_url, is_twitter_url
from app.core.urls.youtube import is_youtube_url
from app.domain.models.source import SourceItem, SourceKind

_THREADS_HOSTS = frozenset({"threads.net", "www.threads.net"})
_INSTAGRAM_HOSTS = frozenset({"instagram.com", "www.instagram.com"})


def classify_url_source_kind(url: str, *, hint: str | None = None) -> SourceKind:
    """Classify a URL into the closest supported source kind."""

    if hint:
        try:
            return SourceKind(hint)
        except ValueError:
            pass

    normalized_url = normalize_url(url)
    if is_youtube_url(normalized_url):
        return SourceKind.YOUTUBE_VIDEO
    if is_twitter_article_url(normalized_url):
        return SourceKind.X_ARTICLE
    if is_twitter_url(normalized_url):
        return SourceKind.X_POST

    parsed = urlparse(normalized_url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if host in _THREADS_HOSTS:
        return SourceKind.THREADS_POST
    if host in _INSTAGRAM_HOSTS:
        if "/reel/" in path or path.startswith(("/reels/", "/tv/")):
            return SourceKind.INSTAGRAM_REEL
        if "/carousel/" in path:
            return SourceKind.INSTAGRAM_CAROUSEL
        if "/p/" in path:
            return SourceKind.INSTAGRAM_POST

    return SourceKind.WEB_ARTICLE


def classify_telegram_message_source_kind(message: Any) -> SourceKind:
    """Classify a Telegram-native submission into the closest source kind."""

    media_group_id = getattr(message, "media_group_id", None)
    has_media = bool(
        getattr(message, "photo", None)
        or getattr(message, "document", None)
        or getattr(message, "video", None)
        or getattr(message, "animation", None)
    )
    if media_group_id and has_media:
        return SourceKind.TELEGRAM_ALBUM
    if has_media:
        return SourceKind.TELEGRAM_POST_WITH_IMAGES
    return SourceKind.TELEGRAM_POST


def build_source_item_from_submission(submission: SourceSubmission) -> SourceItem:
    """Build a classified source item from a raw source submission."""

    metadata = dict(submission.metadata)
    if submission.submission_kind == SourceSubmissionKind.URL:
        url = submission.url or ""
        source_kind = classify_url_source_kind(
            url,
            hint=str(metadata.get("source_kind_hint") or "").strip() or None,
        )
        return SourceItem.create(
            kind=source_kind,
            original_value=url,
            metadata=metadata,
        )

    if submission.submission_kind == SourceSubmissionKind.TELEGRAM_MESSAGE:
        message = submission.telegram_message
        source_kind = classify_telegram_message_source_kind(message)
        title_hint = _extract_telegram_title_hint(message)
        return SourceItem.create(
            kind=source_kind,
            original_value=(
                getattr(message, "text", None) or getattr(message, "caption", None) or ""
            ),
            telegram_chat_id=_coerce_int(getattr(getattr(message, "chat", None), "id", None)),
            telegram_message_id=_coerce_int(
                getattr(message, "id", getattr(message, "message_id", None))
            ),
            telegram_media_group_id=_coerce_str(getattr(message, "media_group_id", None)),
            title_hint=title_hint,
            metadata=metadata,
        )

    return SourceItem.create(kind=SourceKind.UNKNOWN, original_value="")


def _extract_telegram_title_hint(message: Any) -> str | None:
    fwd_chat = getattr(message, "forward_from_chat", None)
    if fwd_chat is not None:
        return _coerce_str(getattr(fwd_chat, "title", None))
    fwd_user = getattr(message, "forward_from", None)
    if fwd_user is not None:
        first_name = _coerce_str(getattr(fwd_user, "first_name", None)) or ""
        last_name = _coerce_str(getattr(fwd_user, "last_name", None)) or ""
        full_name = f"{first_name} {last_name}".strip()
        return full_name or None
    return _coerce_str(getattr(message, "forward_sender_name", None))


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "build_source_item_from_submission",
    "classify_telegram_message_source_kind",
    "classify_url_source_kind",
]
