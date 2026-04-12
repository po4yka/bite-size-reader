"""Shared video-source normalization for YouTube and short-form social video."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from app.application.dto.aggregation import (
    ExtractedTextKind,
    NormalizedSourceDocument,
    SourceMediaAsset,
    SourceMediaKind,
    SourceProvenance,
    SourceTextBlock,
)
from app.core.lang import detect_language

if TYPE_CHECKING:
    from app.domain.models.source import SourceItem


@dataclass(slots=True, frozen=True)
class VideoSourceRequest:
    """Structured input for transcript-first video normalization."""

    source_item: SourceItem
    platform: str
    title: str | None = None
    body_text: str | None = None
    body_kind: ExtractedTextKind = ExtractedTextKind.BODY
    transcript_text: str | None = None
    transcript_source: str | None = None
    audio_transcript_text: str | None = None
    ocr_text: str | None = None
    content_source: str | None = None
    content_text_override: str | None = None
    detected_language: str | None = None
    additional_text_blocks: tuple[SourceTextBlock, ...] = ()
    existing_media: tuple[SourceMediaAsset, ...] = ()
    primary_video_url: str | None = None
    poster_image_urls: tuple[str, ...] = ()
    duration_sec: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    controls: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class VideoSourceExtractionResult:
    """Normalized output for shared video extraction."""

    content_text: str
    content_source: str
    normalized_document: NormalizedSourceDocument
    metadata: dict[str, Any]
    images: list[str]


@runtime_checkable
class VideoSourceExtractor(Protocol):
    """Interface for transcript-first video extraction across platforms."""

    def extract(self, request: VideoSourceRequest) -> VideoSourceExtractionResult:
        """Normalize one video source into content text, media, and provenance."""


class MetadataDrivenVideoSourceExtractor:
    """Build a video-normalized document from extracted metadata and fallback text."""

    def extract(self, request: VideoSourceRequest) -> VideoSourceExtractionResult:
        metadata = dict(request.metadata)
        media = _build_media_assets(request)
        content_text = (
            request.content_text_override
            if request.content_text_override is not None
            else _compose_content_text(request)
        )
        content_source = request.content_source or _default_content_source(request)
        detected_language = request.detected_language or _detect_video_language(
            request, content_text
        )
        primary_fact_source = _resolve_primary_fact_source(request)

        metadata["video_provenance"] = {
            "primary_fact_source": primary_fact_source,
            "available_fact_sources": _available_fact_sources(request),
            "transcript_source": request.transcript_source,
            "frame_ocr_used": bool(_clean_text(request.ocr_text)),
            "audio_transcription_used": bool(_clean_text(request.audio_transcript_text)),
            "content_source": content_source,
        }
        if request.controls:
            metadata["video_controls"] = dict(request.controls)

        normalized_document = NormalizedSourceDocument(
            source_item_id=request.source_item.stable_id,
            source_kind=request.source_item.kind,
            title=request.title or request.source_item.title_hint,
            text=content_text.strip(),
            detected_language=detected_language,
            text_blocks=_build_text_blocks(request),
            media=media,
            metadata=metadata,
            provenance=SourceProvenance(
                source_item_id=request.source_item.stable_id,
                source_kind=request.source_item.kind,
                original_value=request.source_item.original_value,
                normalized_value=request.source_item.normalized_value,
                external_id=request.source_item.external_id,
                request_id=request.source_item.request_id,
                telegram_chat_id=request.source_item.telegram_chat_id,
                telegram_message_id=request.source_item.telegram_message_id,
                telegram_media_group_id=request.source_item.telegram_media_group_id,
                extraction_source=content_source,
                metadata=dict(request.source_item.metadata),
            ),
        )
        return VideoSourceExtractionResult(
            content_text=content_text,
            content_source=content_source,
            normalized_document=normalized_document,
            metadata=metadata,
            images=[
                asset.url for asset in media if asset.kind == SourceMediaKind.IMAGE and asset.url
            ],
        )


def build_video_controls_from_config(cfg: Any) -> dict[str, Any]:
    """Return conservative video limits and fallback settings from runtime config."""

    attachment_cfg = getattr(cfg, "attachment", None)
    youtube_cfg = getattr(cfg, "youtube", None)
    return {
        "storage_path": getattr(
            attachment_cfg,
            "video_storage_path",
            getattr(youtube_cfg, "storage_path", "/data/video-sources"),
        ),
        "cleanup_after_hours": int(
            getattr(
                attachment_cfg,
                "video_cleanup_after_hours",
                getattr(attachment_cfg, "cleanup_after_hours", 24),
            )
        ),
        "max_download_size_mb": int(
            getattr(
                attachment_cfg,
                "video_max_download_size_mb",
                getattr(youtube_cfg, "max_video_size_mb", 500),
            )
        ),
        "timeout_sec": int(getattr(attachment_cfg, "video_timeout_sec", 120)),
        "frame_sample_count": int(getattr(attachment_cfg, "video_frame_sample_count", 4)),
        "audio_transcription_enabled": bool(
            getattr(attachment_cfg, "video_audio_transcription_enabled", True)
        ),
    }


def default_video_controls() -> dict[str, Any]:
    """Fallback limits when no runtime config is available."""

    return {
        "storage_path": "/data/video-sources",
        "cleanup_after_hours": 24,
        "max_download_size_mb": 100,
        "timeout_sec": 120,
        "frame_sample_count": 4,
        "audio_transcription_enabled": True,
    }


def _build_text_blocks(request: VideoSourceRequest) -> list[SourceTextBlock]:
    text_blocks: list[SourceTextBlock] = []
    title = _clean_text(request.title or request.source_item.title_hint)
    if title:
        text_blocks.append(
            SourceTextBlock(kind=ExtractedTextKind.TITLE, text=title, position=len(text_blocks))
        )

    body_text = _clean_text(request.body_text)
    if body_text:
        text_blocks.append(
            SourceTextBlock(
                kind=request.body_kind,
                text=body_text,
                position=len(text_blocks),
                metadata={"fact_source": "body"},
            )
        )

    transcript_text = _clean_text(request.transcript_text)
    if transcript_text:
        text_blocks.append(
            SourceTextBlock(
                kind=ExtractedTextKind.TRANSCRIPT,
                text=transcript_text,
                position=len(text_blocks),
                metadata={
                    "fact_source": "transcript",
                    "transcript_source": request.transcript_source,
                },
            )
        )

    audio_transcript = _clean_text(request.audio_transcript_text)
    if audio_transcript and audio_transcript != transcript_text:
        text_blocks.append(
            SourceTextBlock(
                kind=ExtractedTextKind.TRANSCRIPT,
                text=audio_transcript,
                position=len(text_blocks),
                metadata={"fact_source": "audio_transcript"},
            )
        )

    ocr_text = _clean_text(request.ocr_text)
    if ocr_text:
        text_blocks.append(
            SourceTextBlock(
                kind=ExtractedTextKind.OCR,
                text=ocr_text,
                position=len(text_blocks),
                metadata={"fact_source": "frame_ocr"},
            )
        )

    for block in request.additional_text_blocks:
        text_blocks.append(block.model_copy(update={"position": len(text_blocks)}))

    return text_blocks


def _build_media_assets(request: VideoSourceRequest) -> list[SourceMediaAsset]:
    media: list[SourceMediaAsset] = []
    seen_urls: set[tuple[SourceMediaKind, str]] = set()

    def _append(asset: SourceMediaAsset) -> None:
        if not asset.url:
            return
        key = (asset.kind, asset.url)
        if key in seen_urls:
            return
        seen_urls.add(key)
        media.append(asset.model_copy(update={"position": len(media)}))

    primary_video_url = _clean_text(request.primary_video_url)
    for asset in request.existing_media:
        if (
            asset.kind == SourceMediaKind.VIDEO
            and primary_video_url
            and asset.url == primary_video_url
        ):
            asset = asset.model_copy(
                update={
                    "duration_sec": asset.duration_sec or request.duration_sec,
                    "metadata": {
                        **dict(asset.metadata),
                        "video_role": "primary_video",
                    },
                }
            )
        _append(asset)

    if primary_video_url and not any(
        asset.kind == SourceMediaKind.VIDEO and asset.url == primary_video_url for asset in media
    ):
        _append(
            SourceMediaAsset(
                kind=SourceMediaKind.VIDEO,
                url=primary_video_url,
                duration_sec=request.duration_sec,
                metadata={"video_role": "primary_video"},
            )
        )

    for poster_url in request.poster_image_urls:
        cleaned = _clean_text(poster_url)
        if not cleaned:
            continue
        _append(SourceMediaAsset(kind=SourceMediaKind.IMAGE, url=cleaned))

    return media


def _compose_content_text(request: VideoSourceRequest) -> str:
    parts: list[str] = []
    title = _clean_text(request.title or request.source_item.title_hint)
    if title:
        parts.append(f"Title: {title}")

    body_text = _clean_text(request.body_text)
    if body_text:
        parts.append(body_text)

    transcript_text = _clean_text(request.transcript_text)
    if transcript_text:
        parts.append(f"Transcript:\n{transcript_text}")
    else:
        audio_transcript = _clean_text(request.audio_transcript_text)
        if audio_transcript:
            parts.append(f"Audio transcript fallback:\n{audio_transcript}")

    ocr_text = _clean_text(request.ocr_text)
    if ocr_text:
        parts.append(f"Frame OCR fallback:\n{ocr_text}")

    return "\n\n".join(parts).strip()


def _default_content_source(request: VideoSourceRequest) -> str:
    primary_fact_source = _resolve_primary_fact_source(request)
    return f"video_{primary_fact_source}"


def _resolve_primary_fact_source(request: VideoSourceRequest) -> str:
    if _clean_text(request.transcript_text):
        return "transcript"
    if _clean_text(request.audio_transcript_text):
        return "audio_transcript"
    if _clean_text(request.ocr_text):
        return "frame_ocr"
    if _clean_text(request.body_text):
        return "body"
    return "media_only"


def _available_fact_sources(request: VideoSourceRequest) -> list[str]:
    available: list[str] = []
    if _clean_text(request.body_text):
        available.append("body")
    if _clean_text(request.transcript_text):
        available.append("transcript")
    if _clean_text(request.audio_transcript_text):
        available.append("audio_transcript")
    if _clean_text(request.ocr_text):
        available.append("frame_ocr")
    if request.primary_video_url or request.existing_media:
        available.append("video_media")
    return available


def _detect_video_language(request: VideoSourceRequest, content_text: str) -> str | None:
    sample_parts = [
        _clean_text(request.transcript_text),
        _clean_text(request.audio_transcript_text),
        _clean_text(request.ocr_text),
        _clean_text(request.body_text),
        _clean_text(content_text),
    ]
    sample = "\n".join(part for part in sample_parts if part).strip()
    if not sample:
        return None
    return detect_language(sample)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


__all__ = [
    "MetadataDrivenVideoSourceExtractor",
    "VideoSourceExtractionResult",
    "VideoSourceExtractor",
    "VideoSourceRequest",
    "build_video_controls_from_config",
    "default_video_controls",
]
