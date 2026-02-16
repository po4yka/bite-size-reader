"""Channel digest configuration for scheduled Telegram channel summaries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelDigestConfig(BaseModel):
    """Configuration for the channel digest subsystem.

    Controls the userbot-driven channel reading, LLM analysis,
    and scheduled/on-demand digest delivery.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=False, validation_alias="DIGEST_ENABLED")
    session_name: str = Field(
        default="channel_digest_userbot",
        validation_alias="DIGEST_SESSION_NAME",
    )
    digest_time: str = Field(
        default="09:00",
        validation_alias="DIGEST_TIME",
        description="Daily delivery time (HH:MM)",
    )
    timezone: str = Field(
        default="UTC",
        validation_alias="DIGEST_TIMEZONE",
        description="IANA timezone for scheduler",
    )
    max_posts_per_digest: int = Field(
        default=20,
        validation_alias="DIGEST_MAX_POSTS",
    )
    max_channels: int = Field(
        default=10,
        validation_alias="DIGEST_MAX_CHANNELS",
    )
    concurrency: int = Field(
        default=3,
        validation_alias="DIGEST_CONCURRENCY",
        description="Parallel LLM semaphore limit",
    )
    min_post_length: int = Field(
        default=100,
        validation_alias="DIGEST_MIN_POST_LENGTH",
        description="Skip posts shorter than this (chars)",
    )
    hours_lookback: int = Field(
        default=24,
        validation_alias="DIGEST_HOURS_LOOKBACK",
        description="Fetch window in hours",
    )
    max_posts_per_channel: int = Field(
        default=5,
        validation_alias="DIGEST_MAX_POSTS_PER_CHANNEL",
        description="Max posts taken from a single channel",
    )
    min_relevance_score: float = Field(
        default=0.3,
        validation_alias="DIGEST_MIN_RELEVANCE",
        description="Drop posts below this relevance score",
    )

    @field_validator("session_name", mode="before")
    @classmethod
    def _validate_session_name(cls, value: Any) -> str:
        name = str(value or "channel_digest_userbot").strip()
        if not name:
            return "channel_digest_userbot"
        if len(name) > 100:
            msg = "Digest session name is too long"
            raise ValueError(msg)
        return name

    @field_validator("digest_time", mode="before")
    @classmethod
    def _validate_digest_time(cls, value: Any) -> str:
        raw = str(value or "09:00").strip()
        if not raw:
            return "09:00"
        parts = raw.split(":")
        if len(parts) != 2:
            msg = "DIGEST_TIME must be in HH:MM format"
            raise ValueError(msg)
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError as exc:
            msg = "DIGEST_TIME must contain valid integers"
            raise ValueError(msg) from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            msg = "DIGEST_TIME hour must be 0-23 and minute must be 0-59"
            raise ValueError(msg)
        return raw

    @field_validator("timezone", mode="before")
    @classmethod
    def _validate_timezone(cls, value: Any) -> str:
        tz = str(value or "UTC").strip()
        if not tz:
            return "UTC"
        if len(tz) > 50:
            msg = "Digest timezone value is too long"
            raise ValueError(msg)
        return tz

    @field_validator("max_posts_per_digest", mode="before")
    @classmethod
    def _validate_max_posts(cls, value: Any) -> int:
        if value in (None, ""):
            return 20
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_MAX_POSTS must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = "DIGEST_MAX_POSTS must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("max_channels", mode="before")
    @classmethod
    def _validate_max_channels(cls, value: Any) -> int:
        if value in (None, ""):
            return 10
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_MAX_CHANNELS must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 50:
            msg = "DIGEST_MAX_CHANNELS must be between 1 and 50"
            raise ValueError(msg)
        return parsed

    @field_validator("concurrency", mode="before")
    @classmethod
    def _validate_concurrency(cls, value: Any) -> int:
        if value in (None, ""):
            return 3
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_CONCURRENCY must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 10:
            msg = "DIGEST_CONCURRENCY must be between 1 and 10"
            raise ValueError(msg)
        return parsed

    @field_validator("min_post_length", mode="before")
    @classmethod
    def _validate_min_post_length(cls, value: Any) -> int:
        if value in (None, ""):
            return 100
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_MIN_POST_LENGTH must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 5000:
            msg = "DIGEST_MIN_POST_LENGTH must be between 0 and 5000"
            raise ValueError(msg)
        return parsed

    @field_validator("hours_lookback", mode="before")
    @classmethod
    def _validate_hours_lookback(cls, value: Any) -> int:
        if value in (None, ""):
            return 24
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_HOURS_LOOKBACK must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 168:
            msg = "DIGEST_HOURS_LOOKBACK must be between 1 and 168 hours"
            raise ValueError(msg)
        return parsed

    @field_validator("max_posts_per_channel", mode="before")
    @classmethod
    def _validate_max_posts_per_channel(cls, value: Any) -> int:
        if value in (None, ""):
            return 5
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "DIGEST_MAX_POSTS_PER_CHANNEL must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 20:
            msg = "DIGEST_MAX_POSTS_PER_CHANNEL must be between 1 and 20"
            raise ValueError(msg)
        return parsed

    @field_validator("min_relevance_score", mode="before")
    @classmethod
    def _validate_min_relevance_score(cls, value: Any) -> float:
        if value in (None, ""):
            return 0.3
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "DIGEST_MIN_RELEVANCE must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0.0 or parsed > 1.0:
            msg = "DIGEST_MIN_RELEVANCE must be between 0.0 and 1.0"
            raise ValueError(msg)
        return parsed
