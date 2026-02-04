from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

logger = logging.getLogger(__name__)


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


class KarakeepConfig(BaseModel):
    """Karakeep integration configuration for bookmark synchronization."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=False, validation_alias="KARAKEEP_ENABLED")
    api_url: str = Field(
        default="http://localhost:3000/api/v1",
        validation_alias="KARAKEEP_API_URL",
    )
    api_key: str = Field(default="", validation_alias="KARAKEEP_API_KEY")
    sync_tag: str = Field(default="bsr-synced", validation_alias="KARAKEEP_SYNC_TAG")
    sync_interval_hours: int = Field(default=6, validation_alias="KARAKEEP_SYNC_INTERVAL_HOURS")
    auto_sync_enabled: bool = Field(default=True, validation_alias="KARAKEEP_AUTO_SYNC_ENABLED")

    @field_validator("api_url", mode="before")
    @classmethod
    def _validate_api_url(cls, value: Any) -> str:
        url = str(value or "http://localhost:3000/api/v1").strip()
        if not url:
            return "http://localhost:3000/api/v1"
        return url.rstrip("/")

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        key = str(value).strip()
        if len(key) > 500:
            msg = "Karakeep API key appears to be too long"
            raise ValueError(msg)
        return key

    @field_validator("sync_tag", mode="before")
    @classmethod
    def _validate_sync_tag(cls, value: Any) -> str:
        tag = str(value or "bsr-synced").strip()
        if not tag:
            return "bsr-synced"
        if len(tag) > 50:
            msg = "Karakeep sync tag is too long"
            raise ValueError(msg)
        return tag

    @field_validator("sync_interval_hours", mode="before")
    @classmethod
    def _validate_sync_interval(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 6))
        except ValueError as exc:
            msg = "Karakeep sync interval must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 168:
            msg = "Karakeep sync interval must be between 1 and 168 hours"
            raise ValueError(msg)
        return parsed


class WebSearchConfig(BaseModel):
    """Web search enrichment configuration for LLM summarization."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=False,
        validation_alias="WEB_SEARCH_ENABLED",
        description="Enable web search enrichment for summaries (opt-in)",
    )
    max_queries: int = Field(
        default=3,
        validation_alias="WEB_SEARCH_MAX_QUERIES",
        description="Maximum search queries per article",
    )
    min_content_length: int = Field(
        default=500,
        validation_alias="WEB_SEARCH_MIN_CONTENT_LENGTH",
        description="Minimum content length (chars) to trigger search",
    )
    timeout_sec: float = Field(
        default=10.0,
        validation_alias="WEB_SEARCH_TIMEOUT_SEC",
        description="Timeout for search operations in seconds",
    )
    max_context_chars: int = Field(
        default=2000,
        validation_alias="WEB_SEARCH_MAX_CONTEXT_CHARS",
        description="Maximum characters for injected search context",
    )
    cache_ttl_sec: int = Field(
        default=3600,
        validation_alias="WEB_SEARCH_CACHE_TTL_SEC",
        description="Cache TTL for search results in seconds",
    )

    @field_validator("max_queries", mode="before")
    @classmethod
    def _validate_max_queries(cls, value: Any) -> int:
        if value in (None, ""):
            return 3
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Max queries must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 10:
            msg = "Max queries must be between 1 and 10"
            raise ValueError(msg)
        return parsed

    @field_validator("min_content_length", mode="before")
    @classmethod
    def _validate_min_content_length(cls, value: Any) -> int:
        if value in (None, ""):
            return 500
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Min content length must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 10000:
            msg = "Min content length must be between 0 and 10000"
            raise ValueError(msg)
        return parsed

    @field_validator("timeout_sec", mode="before")
    @classmethod
    def _validate_timeout_sec(cls, value: Any) -> float:
        if value in (None, ""):
            return 10.0
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 1.0 or parsed > 60.0:
            msg = "Timeout must be between 1 and 60 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("max_context_chars", mode="before")
    @classmethod
    def _validate_max_context_chars(cls, value: Any) -> int:
        if value in (None, ""):
            return 2000
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Max context chars must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 500 or parsed > 10000:
            msg = "Max context chars must be between 500 and 10000"
            raise ValueError(msg)
        return parsed

    @field_validator("cache_ttl_sec", mode="before")
    @classmethod
    def _validate_cache_ttl_sec(cls, value: Any) -> int:
        if value in (None, ""):
            return 3600
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Cache TTL must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 60 or parsed > 86400:
            msg = "Cache TTL must be between 60 and 86400 seconds"
            raise ValueError(msg)
        return parsed
