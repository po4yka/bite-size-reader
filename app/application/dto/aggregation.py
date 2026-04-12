"""Application DTOs for mixed-source aggregation."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models.source import SourceKind  # noqa: TC001

if TYPE_CHECKING:
    from app.domain.models.source import SourceItem


class ExtractedTextKind(StrEnum):
    """Kinds of extracted text blocks that can compose a normalized source."""

    BODY = "body"
    TITLE = "title"
    CAPTION = "caption"
    TRANSCRIPT = "transcript"
    OCR = "ocr"
    ALT_TEXT = "alt_text"


class SourceMediaKind(StrEnum):
    """Media kinds that can be attached to a normalized source document."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class SourceSubmissionKind(StrEnum):
    """Kinds of raw bundle submissions accepted by the orchestrator."""

    URL = "url"
    TELEGRAM_MESSAGE = "telegram_message"


class SourceSubmission(BaseModel):
    """Raw bundle item before source classification and extraction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    submission_kind: SourceSubmissionKind
    url: str | None = None
    telegram_message: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> SourceSubmission:
        if self.submission_kind == SourceSubmissionKind.URL:
            if not self.url or not self.url.strip():
                msg = "URL source submissions require a non-empty URL"
                raise ValueError(msg)
            return self
        if self.submission_kind == SourceSubmissionKind.TELEGRAM_MESSAGE:
            if self.telegram_message is None:
                msg = "Telegram source submissions require a message payload"
                raise ValueError(msg)
            return self

        msg = f"Unsupported source submission kind: {self.submission_kind}"
        raise ValueError(msg)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSubmission:
        return cls(
            submission_kind=SourceSubmissionKind.URL,
            url=url,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_telegram_message(
        cls,
        telegram_message: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSubmission:
        return cls(
            submission_kind=SourceSubmissionKind.TELEGRAM_MESSAGE,
            telegram_message=telegram_message,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_telegram_messages(
        cls,
        telegram_messages: list[Any] | tuple[Any, ...],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> SourceSubmission:
        return cls(
            submission_kind=SourceSubmissionKind.TELEGRAM_MESSAGE,
            telegram_message=list(telegram_messages),
            metadata=dict(metadata or {}),
        )


class AggregationFailure(BaseModel):
    """Shared failure payload for bundle-level and item-level errors."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class SourceTextBlock(BaseModel):
    """One extracted text segment with source-aware typing."""

    model_config = ConfigDict(frozen=True)

    kind: ExtractedTextKind = ExtractedTextKind.BODY
    text: str
    position: int | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Source text blocks cannot be empty"
            raise ValueError(msg)
        return stripped


class SourceMediaAsset(BaseModel):
    """Normalized media descriptor for multimodal aggregation."""

    model_config = ConfigDict(frozen=True)

    kind: SourceMediaKind
    url: str | None = None
    local_path: str | None = None
    mime_type: str | None = None
    alt_text: str | None = None
    position: int | None = None
    duration_sec: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_locator(self) -> SourceMediaAsset:
        if not (self.url or self.local_path):
            msg = "Source media assets require either a URL or a local path"
            raise ValueError(msg)
        return self


class SourceProvenance(BaseModel):
    """Stable provenance metadata for an extracted source document."""

    model_config = ConfigDict(frozen=True)

    source_item_id: str
    source_kind: SourceKind
    original_value: str | None = None
    normalized_value: str | None = None
    external_id: str | None = None
    request_id: int | None = None
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None
    telegram_media_group_id: str | None = None
    extraction_source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedSourceDocument(BaseModel):
    """Shared extractor output contract for text, media, and provenance."""

    model_config = ConfigDict(frozen=True)

    source_item_id: str
    source_kind: SourceKind
    title: str | None = None
    text: str = ""
    detected_language: str | None = None
    text_blocks: list[SourceTextBlock] = Field(default_factory=list)
    media: list[SourceMediaAsset] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: SourceProvenance

    @model_validator(mode="after")
    def validate_content(self) -> NormalizedSourceDocument:
        has_text = bool(self.text.strip()) or any(block.text.strip() for block in self.text_blocks)
        if not has_text and not self.media:
            msg = "Normalized source documents require extracted text or media"
            raise ValueError(msg)
        return self

    @classmethod
    def from_extracted_content(
        cls,
        *,
        source_item: SourceItem,
        text: str = "",
        title: str | None = None,
        detected_language: str | None = None,
        content_source: str | None = None,
        media_urls: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        text_kind: ExtractedTextKind = ExtractedTextKind.BODY,
    ) -> NormalizedSourceDocument:
        """Build a normalized document from existing extractor output."""

        document_metadata = dict(metadata or {})
        if content_source:
            document_metadata.setdefault("content_source", content_source)

        text_blocks: list[SourceTextBlock] = []
        if title:
            text_blocks.append(
                SourceTextBlock(kind=ExtractedTextKind.TITLE, text=title, position=0)
            )
        if text.strip():
            text_blocks.append(
                SourceTextBlock(
                    kind=text_kind,
                    text=text,
                    position=len(text_blocks),
                )
            )

        media = [
            SourceMediaAsset(kind=SourceMediaKind.IMAGE, url=url, position=index)
            for index, url in enumerate(media_urls or [])
            if url
        ]
        return cls(
            source_item_id=source_item.stable_id,
            source_kind=source_item.kind,
            title=title,
            text=text.strip(),
            detected_language=detected_language,
            text_blocks=text_blocks,
            media=media,
            metadata=document_metadata,
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
                extraction_source=content_source,
                metadata=dict(source_item.metadata),
            ),
        )


class SourceExtractionItemResult(BaseModel):
    """Item-level extraction result ready for bundle synthesis."""

    model_config = ConfigDict(frozen=True)

    position: int
    item_id: int
    source_item_id: str
    source_kind: SourceKind
    status: str
    request_id: int | None = None
    duplicate_of_item_id: int | None = None
    normalized_document: NormalizedSourceDocument | None = None
    failure: AggregationFailure | None = None
    extraction_metadata: dict[str, Any] = Field(default_factory=dict)


class MultiSourceExtractionOutput(BaseModel):
    """Bundle extraction output with per-item results."""

    model_config = ConfigDict(frozen=True)

    session_id: int
    correlation_id: str
    status: str
    successful_count: int
    failed_count: int
    duplicate_count: int
    items: list[SourceExtractionItemResult] = Field(default_factory=list)


__all__ = [
    "AggregationFailure",
    "ExtractedTextKind",
    "MultiSourceExtractionOutput",
    "NormalizedSourceDocument",
    "SourceExtractionItemResult",
    "SourceMediaAsset",
    "SourceMediaKind",
    "SourceProvenance",
    "SourceSubmission",
    "SourceSubmissionKind",
    "SourceTextBlock",
]
