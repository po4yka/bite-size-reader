"""Shared Telegram multimodal extraction helpers."""

from __future__ import annotations

from typing import Any

from app.application.dto.aggregation import (
    ExtractedTextKind,
    NormalizedSourceDocument,
    SourceMediaAsset,
    SourceMediaKind,
    SourceProvenance,
    SourceTextBlock,
)
from app.domain.models.source import SourceItem, SourceKind


def coerce_telegram_messages(payload: Any) -> list[Any]:
    """Normalize a Telegram payload into an ordered list of message objects."""

    if payload is None:
        msg = "Telegram payload cannot be empty"
        raise ValueError(msg)
    if isinstance(payload, list | tuple):
        messages = [message for message in payload if message is not None]
    else:
        messages = [payload]
    if not messages:
        msg = "Telegram payload cannot be empty"
        raise ValueError(msg)
    return sorted(messages, key=_message_sort_key)


def classify_telegram_messages_source_kind(payload: Any) -> SourceKind:
    """Classify one Telegram message or an album payload."""

    messages = coerce_telegram_messages(payload)
    primary_message = messages[0]
    media_group_id = _coerce_str(getattr(primary_message, "media_group_id", None))
    has_media = any(_has_supported_media(message) for message in messages)
    if media_group_id and has_media:
        return SourceKind.TELEGRAM_ALBUM
    if has_media:
        return SourceKind.TELEGRAM_POST_WITH_IMAGES
    return SourceKind.TELEGRAM_POST


def build_source_item_from_telegram_payload(
    payload: Any,
    *,
    metadata: dict[str, Any] | None = None,
) -> SourceItem:
    """Build a stable source item for a Telegram message or album."""

    messages = coerce_telegram_messages(payload)
    primary_message = messages[0]
    message_ids = [_coerce_int(_message_id(message)) for message in messages]
    source_metadata = dict(metadata or {})
    source_metadata.setdefault(
        "message_ids",
        [message_id for message_id in message_ids if message_id is not None],
    )
    source_metadata.setdefault("media_count", len(build_telegram_media_assets(messages)))
    source_metadata.setdefault(
        "video_processing_strategy",
        "deferred_to_phase6"
        if any(getattr(message, "video", None) for message in messages)
        else None,
    )
    return SourceItem.create(
        kind=classify_telegram_messages_source_kind(messages),
        original_value=combine_telegram_text(messages) or "",
        telegram_chat_id=_coerce_int(getattr(getattr(primary_message, "chat", None), "id", None)),
        telegram_message_id=_coerce_int(_message_id(primary_message)),
        telegram_media_group_id=_coerce_str(getattr(primary_message, "media_group_id", None)),
        title_hint=extract_telegram_title_hint(messages),
        metadata={k: v for k, v in source_metadata.items() if v is not None},
    )


def build_telegram_normalized_document(
    payload: Any,
    *,
    source_item: SourceItem,
) -> tuple[NormalizedSourceDocument, dict[str, Any]]:
    """Build a normalized Telegram source document from one message or an album."""

    messages = coerce_telegram_messages(payload)
    text = combine_telegram_text(messages)
    media = build_telegram_media_assets(messages)
    metadata = build_telegram_extraction_metadata(messages)
    if not text and not media:
        msg = "Telegram submission has neither text nor supported media metadata"
        raise ValueError(msg)

    text_blocks = build_telegram_text_blocks(messages, source_item.title_hint)
    document = NormalizedSourceDocument(
        source_item_id=source_item.stable_id,
        source_kind=source_item.kind,
        title=source_item.title_hint,
        text=text or "",
        detected_language=None,
        text_blocks=text_blocks,
        media=media,
        metadata=metadata,
        provenance=SourceProvenance(
            source_item_id=source_item.stable_id,
            source_kind=source_item.kind,
            original_value=source_item.original_value,
            normalized_value=source_item.normalized_value,
            external_id=source_item.external_id,
            request_id=source_item.request_id,
            telegram_chat_id=source_item.telegram_chat_id,
            telegram_message_id=source_item.telegram_message_id,
            telegram_media_group_id=source_item.telegram_media_group_id,
            extraction_source="telegram_native",
            metadata=dict(source_item.metadata),
        ),
    )
    return document, metadata


def combine_telegram_text(payload: Any) -> str | None:
    """Combine distinct Telegram text/caption segments in message order."""

    messages = coerce_telegram_messages(payload)
    parts: list[str] = []
    seen: set[str] = set()
    for message in messages:
        text = _coerce_str(getattr(message, "text", None) or getattr(message, "caption", None))
        if not text or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


def build_telegram_text_blocks(
    payload: Any,
    title_hint: str | None,
) -> list[SourceTextBlock]:
    """Build ordered text blocks for Telegram-native content."""

    messages = coerce_telegram_messages(payload)
    text_blocks: list[SourceTextBlock] = []
    if title_hint:
        text_blocks.append(
            SourceTextBlock(
                kind=ExtractedTextKind.TITLE,
                text=title_hint,
                position=0,
            )
        )

    for message in messages:
        text = _coerce_str(getattr(message, "text", None) or getattr(message, "caption", None))
        if not text:
            continue
        text_blocks.append(
            SourceTextBlock(
                kind=(
                    ExtractedTextKind.CAPTION
                    if getattr(message, "caption", None)
                    else ExtractedTextKind.BODY
                ),
                text=text,
                position=len(text_blocks),
                metadata={
                    "telegram_message_id": _coerce_int(_message_id(message)),
                    "media_group_id": _coerce_str(getattr(message, "media_group_id", None)),
                },
            )
        )
    return text_blocks


def build_telegram_media_assets(payload: Any) -> list[SourceMediaAsset]:
    """Build ordered media assets for Telegram-native content."""

    messages = coerce_telegram_messages(payload)
    assets: list[SourceMediaAsset] = []
    for message in messages:
        assets.extend(_build_message_media_assets(message, base_position=len(assets)))
    return assets


def build_telegram_extraction_metadata(payload: Any) -> dict[str, Any]:
    """Build provenance-rich extraction metadata for Telegram-native content."""

    messages = coerce_telegram_messages(payload)
    primary_message = messages[0]
    forward_from_chat = getattr(primary_message, "forward_from_chat", None)
    forward_from_user = getattr(primary_message, "forward_from", None)
    return {
        "chat_id": _coerce_int(getattr(getattr(primary_message, "chat", None), "id", None)),
        "message_id": _coerce_int(_message_id(primary_message)),
        "message_ids": [
            message_id
            for message_id in (_coerce_int(_message_id(message)) for message in messages)
            if message_id is not None
        ],
        "media_group_id": _coerce_str(getattr(primary_message, "media_group_id", None)),
        "forward_from_chat_id": _coerce_int(getattr(forward_from_chat, "id", None)),
        "forward_from_chat_title": getattr(forward_from_chat, "title", None),
        "forward_from_message_id": _coerce_int(
            getattr(primary_message, "forward_from_message_id", None)
        ),
        "forward_from_user_id": _coerce_int(getattr(forward_from_user, "id", None)),
        "forward_from_user_name": _build_forward_user_name(forward_from_user),
        "forward_sender_name": _coerce_str(getattr(primary_message, "forward_sender_name", None)),
        "media_count": len(build_telegram_media_assets(messages)),
        "video_processing_strategy": (
            "deferred_to_phase6"
            if any(getattr(message, "video", None) for message in messages)
            else None
        ),
    }


def extract_telegram_title_hint(payload: Any) -> str | None:
    """Extract the best available title/source label for Telegram-native content."""

    primary_message = coerce_telegram_messages(payload)[0]
    fwd_chat = getattr(primary_message, "forward_from_chat", None)
    if fwd_chat is not None:
        return _coerce_str(getattr(fwd_chat, "title", None))
    fwd_user = getattr(primary_message, "forward_from", None)
    if fwd_user is not None:
        return _build_forward_user_name(fwd_user)
    return _coerce_str(getattr(primary_message, "forward_sender_name", None))


def build_telegram_summary_context(payload: Any) -> str | None:
    """Build user-facing context text for multimodal Telegram summaries."""

    messages = coerce_telegram_messages(payload)
    title = extract_telegram_title_hint(messages)
    text = combine_telegram_text(messages)
    header = None
    if title:
        source_label = (
            "Forwarded from" if getattr(messages[0], "forward_from_chat", None) else "Source"
        )
        header = f"{source_label}: {title}"
    if header and text:
        return f"{header}\n\n{text}"
    return header or text


def _build_message_media_assets(message: Any, *, base_position: int) -> list[SourceMediaAsset]:
    assets: list[SourceMediaAsset] = []
    photo = getattr(message, "photo", None)
    if photo is not None:
        photo_items = photo if isinstance(photo, list) else [photo]
        if photo_items:
            item = photo_items[-1]
            file_id = getattr(item, "file_id", None)
            if file_id:
                assets.append(
                    SourceMediaAsset(
                        kind=SourceMediaKind.IMAGE,
                        url=f"telegram://file/{file_id}",
                        position=base_position + len(assets),
                        metadata={
                            "telegram_file_id": file_id,
                            "width": _coerce_int(getattr(item, "width", None)),
                            "height": _coerce_int(getattr(item, "height", None)),
                            "telegram_message_id": _coerce_int(_message_id(message)),
                        },
                    )
                )

    document = getattr(message, "document", None)
    if document is not None:
        file_id = getattr(document, "file_id", None)
        mime_type = getattr(document, "mime_type", None)
        if file_id:
            assets.append(
                SourceMediaAsset(
                    kind=_media_kind_for_mime(mime_type),
                    url=f"telegram://file/{file_id}",
                    position=base_position + len(assets),
                    mime_type=str(mime_type) if mime_type else None,
                    metadata={
                        "telegram_file_id": file_id,
                        "file_name": getattr(document, "file_name", None),
                        "telegram_message_id": _coerce_int(_message_id(message)),
                    },
                )
            )

    for field_name, media_kind in (
        ("video", SourceMediaKind.VIDEO),
        ("animation", SourceMediaKind.VIDEO),
    ):
        media = getattr(message, field_name, None)
        if media is None:
            continue
        file_id = getattr(media, "file_id", None)
        if file_id:
            assets.append(
                SourceMediaAsset(
                    kind=media_kind,
                    url=f"telegram://file/{file_id}",
                    position=base_position + len(assets),
                    mime_type="video/mp4",
                    metadata={
                        "telegram_file_id": file_id,
                        "duration": _coerce_int(getattr(media, "duration", None)),
                        "telegram_message_id": _coerce_int(_message_id(message)),
                    },
                )
            )

    return assets


def _media_kind_for_mime(mime_type: Any) -> SourceMediaKind:
    mime = str(mime_type or "").strip().lower()
    if mime.startswith("image/"):
        return SourceMediaKind.IMAGE
    if mime.startswith("video/"):
        return SourceMediaKind.VIDEO
    if mime.startswith("audio/"):
        return SourceMediaKind.AUDIO
    return SourceMediaKind.DOCUMENT


def _has_supported_media(message: Any) -> bool:
    return bool(
        getattr(message, "photo", None)
        or getattr(message, "document", None)
        or getattr(message, "video", None)
        or getattr(message, "animation", None)
    )


def _message_sort_key(message: Any) -> tuple[int, str]:
    message_id = _coerce_int(_message_id(message))
    return (message_id or 0, str(getattr(message, "media_group_id", "") or ""))


def _message_id(message: Any) -> Any:
    return getattr(message, "id", getattr(message, "message_id", None))


def _build_forward_user_name(forward_from_user: Any) -> str | None:
    if forward_from_user is None:
        return None
    first_name = _coerce_str(getattr(forward_from_user, "first_name", None)) or ""
    last_name = _coerce_str(getattr(forward_from_user, "last_name", None)) or ""
    full_name = f"{first_name} {last_name}".strip()
    return full_name or None


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
    "build_source_item_from_telegram_payload",
    "build_telegram_extraction_metadata",
    "build_telegram_media_assets",
    "build_telegram_normalized_document",
    "build_telegram_summary_context",
    "build_telegram_text_blocks",
    "classify_telegram_messages_source_kind",
    "coerce_telegram_messages",
    "combine_telegram_text",
    "extract_telegram_title_hint",
]
