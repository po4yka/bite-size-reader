from __future__ import annotations

from app.adapters.video.source_extractor import (
    MetadataDrivenVideoSourceExtractor,
    VideoSourceRequest,
)
from app.application.dto.aggregation import (
    ExtractedTextKind,
    SourceMediaAsset,
    SourceMediaKind,
)
from app.domain.models.source import SourceItem, SourceKind


def test_video_source_extractor_prefers_transcript_and_tracks_provenance() -> None:
    source_item = SourceItem.create(
        kind=SourceKind.INSTAGRAM_REEL,
        original_value="https://www.instagram.com/reel/DAreel456/",
        external_id="DAreel456",
    )

    result = MetadataDrivenVideoSourceExtractor().extract(
        VideoSourceRequest(
            source_item=source_item,
            platform="meta",
            title="Reel title",
            body_text="Caption text",
            body_kind=ExtractedTextKind.CAPTION,
            transcript_text="Primary transcript",
            transcript_source="subtitle_api",
            audio_transcript_text="Audio fallback",
            ocr_text="Frame OCR fallback",
            content_source="meta_video",
            existing_media=(
                SourceMediaAsset(
                    kind=SourceMediaKind.VIDEO,
                    url="https://cdn.example.com/reel.mp4",
                ),
                SourceMediaAsset(
                    kind=SourceMediaKind.IMAGE,
                    url="https://cdn.example.com/poster.jpg",
                ),
            ),
            controls={"timeout_sec": 90},
            metadata={"platform": "instagram"},
        )
    )

    assert result.content_source == "meta_video"
    assert "Primary transcript" in result.content_text
    assert result.normalized_document.text_blocks[1].kind == ExtractedTextKind.CAPTION
    assert result.normalized_document.text_blocks[2].kind == ExtractedTextKind.TRANSCRIPT
    assert result.metadata["video_provenance"]["primary_fact_source"] == "transcript"
    assert result.metadata["video_controls"]["timeout_sec"] == 90
    assert result.images == ["https://cdn.example.com/poster.jpg"]


def test_video_source_extractor_allows_media_only_video_documents() -> None:
    source_item = SourceItem.create(
        kind=SourceKind.TELEGRAM_POST_WITH_IMAGES,
        original_value="",
        telegram_chat_id=-100777,
        telegram_message_id=501,
    )

    result = MetadataDrivenVideoSourceExtractor().extract(
        VideoSourceRequest(
            source_item=source_item,
            platform="telegram",
            existing_media=(
                SourceMediaAsset(
                    kind=SourceMediaKind.VIDEO,
                    url="telegram://file/video-1",
                ),
            ),
            primary_video_url="telegram://file/video-1",
            content_source="telegram_video_native",
        )
    )

    assert result.content_text == ""
    assert result.normalized_document.media[0].kind == SourceMediaKind.VIDEO
    assert result.metadata["video_provenance"]["primary_fact_source"] == "media_only"
