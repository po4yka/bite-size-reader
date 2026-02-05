from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class YouTubeConfig(BaseModel):
    """YouTube video download and storage configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="YOUTUBE_DOWNLOAD_ENABLED",
        description="Enable YouTube video downloading",
    )

    storage_path: str = Field(
        default="/data/videos",
        validation_alias="YOUTUBE_STORAGE_PATH",
        description="Path to store downloaded videos",
    )

    max_video_size_mb: int = Field(
        default=500,
        validation_alias="YOUTUBE_MAX_VIDEO_SIZE_MB",
        description="Maximum video file size in MB",
    )

    max_storage_gb: int = Field(
        default=100,
        validation_alias="YOUTUBE_MAX_STORAGE_GB",
        description="Maximum total storage for videos in GB",
    )

    auto_cleanup_enabled: bool = Field(
        default=True,
        validation_alias="YOUTUBE_AUTO_CLEANUP_ENABLED",
        description="Enable automatic cleanup of old videos",
    )

    cleanup_after_days: int = Field(
        default=30,
        validation_alias="YOUTUBE_CLEANUP_AFTER_DAYS",
        description="Delete videos older than this many days",
    )

    preferred_quality: str = Field(
        default="1080p",
        validation_alias="YOUTUBE_PREFERRED_QUALITY",
        description="Preferred video quality (1080p, 720p, 480p)",
    )

    subtitle_languages: list[str] = Field(
        default=["en", "ru"],
        validation_alias="YOUTUBE_SUBTITLE_LANGUAGES",
        description="Preferred subtitle languages (fallback order)",
    )

    @field_validator("subtitle_languages", mode="before")
    @classmethod
    def _parse_subtitle_languages(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [lang.strip() for lang in value.split(",") if lang.strip()]
        return ["en", "ru"]

    @field_validator("max_video_size_mb", "max_storage_gb", "cleanup_after_days", mode="before")
    @classmethod
    def _parse_int_fields(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            return int(default)
        try:
            return int(str(value))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc

    @field_validator("preferred_quality", mode="before")
    @classmethod
    def _validate_preferred_quality(cls, value: Any) -> str:
        if value in (None, ""):
            return "1080p"
        valid_qualities = {"1080p", "720p", "480p", "360p", "240p"}
        value_str = str(value).lower().strip()
        if value_str not in valid_qualities:
            msg = f"preferred_quality must be one of: {', '.join(sorted(valid_qualities))}"
            raise ValueError(msg)
        return value_str


class AttachmentConfig(BaseModel):
    """Attachment processing configuration for images and PDFs."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="ATTACHMENT_PROCESSING_ENABLED",
        description="Enable attachment processing (images, PDFs)",
    )

    vision_model: str = Field(
        default="google/gemini-3-flash-preview",
        validation_alias="ATTACHMENT_VISION_MODEL",
        description="Vision-capable model for image and scanned PDF analysis",
    )

    max_image_size_mb: int = Field(
        default=10,
        validation_alias="ATTACHMENT_MAX_IMAGE_SIZE_MB",
        description="Maximum image file size in MB",
    )

    max_pdf_size_mb: int = Field(
        default=20,
        validation_alias="ATTACHMENT_MAX_PDF_SIZE_MB",
        description="Maximum PDF file size in MB",
    )

    max_pdf_pages: int = Field(
        default=50,
        validation_alias="ATTACHMENT_MAX_PDF_PAGES",
        description="Maximum PDF pages to process",
    )

    image_max_dimension: int = Field(
        default=2048,
        validation_alias="ATTACHMENT_IMAGE_MAX_DIMENSION",
        description="Maximum image dimension (width or height) before resizing",
    )

    storage_path: str = Field(
        default="/data/attachments",
        validation_alias="ATTACHMENT_STORAGE_PATH",
        description="Temporary storage path for downloaded attachments",
    )

    cleanup_after_hours: int = Field(
        default=24,
        validation_alias="ATTACHMENT_CLEANUP_AFTER_HOURS",
        description="Delete attachment files after this many hours",
    )

    max_vision_pages_per_pdf: int = Field(
        default=5,
        validation_alias="ATTACHMENT_MAX_VISION_PAGES",
        description="Maximum number of sparse/scanned PDF pages to render for vision LLM",
    )

    @field_validator(
        "max_image_size_mb",
        "max_pdf_size_mb",
        "max_pdf_pages",
        "image_max_dimension",
        "cleanup_after_hours",
        "max_vision_pages_per_pdf",
        mode="before",
    )
    @classmethod
    def _parse_int_fields(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            return int(default)
        try:
            return int(str(value))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
