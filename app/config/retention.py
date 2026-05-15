"""Retention policy configuration for raw artifact purge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class RetentionConfig(BaseModel):
    """Per-subsystem TTL-based raw-data retention policy.

    A TTL of 0 means "never purge" for that subsystem.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="RETENTION_ENABLED",
        description="Master switch; when False no purge runs.",
    )
    cron: str = Field(
        default="0 3 * * *",
        validation_alias="RETENTION_CRON",
        description="UTC cron expression for the daily purge job.",
    )
    batch_size: int = Field(
        default=500,
        validation_alias="RETENTION_BATCH_SIZE",
        description="Max rows updated per subsystem per run.",
    )
    telegram_raw_days: int = Field(
        default=30,
        validation_alias="RETENTION_TELEGRAM_RAW_DAYS",
        description="Days to keep telegram_messages raw columns. 0 = never purge.",
    )
    crawl_content_days: int = Field(
        default=7,
        validation_alias="RETENTION_CRAWL_CONTENT_DAYS",
        description="Days to keep crawl_results content columns. 0 = never purge.",
    )
    llm_payload_days: int = Field(
        default=90,
        validation_alias="RETENTION_LLM_PAYLOAD_DAYS",
        description="Days to keep llm_calls request/response columns. 0 = never purge.",
    )
    video_transcript_days: int = Field(
        default=30,
        validation_alias="RETENTION_VIDEO_TRANSCRIPT_DAYS",
        description="Days to keep video_downloads.transcript_text. 0 = never purge.",
    )
    interaction_text_days: int = Field(
        default=30,
        validation_alias="RETENTION_INTERACTION_TEXT_DAYS",
        description="Days to keep user_interactions.input_text. 0 = never purge.",
    )
    request_content_days: int = Field(
        default=30,
        validation_alias="RETENTION_REQUEST_CONTENT_DAYS",
        description="Days to keep requests.content_text + error_context_json. 0 = never purge.",
    )

    @field_validator("cron", mode="before")
    @classmethod
    def _validate_cron(cls, value: Any) -> str:
        if value in (None, ""):
            return "0 3 * * *"
        cron = str(value).strip()
        if len(cron.split()) != 5:
            msg = "Retention cron must be a valid 5-field cron expression"
            raise ValueError(msg)
        return cron

    @field_validator("batch_size", mode="before")
    @classmethod
    def _validate_batch_size(cls, value: Any) -> int:
        parsed = int(str(value)) if value not in (None, "") else 500
        if parsed < 1 or parsed > 10_000:
            msg = "Retention batch_size must be between 1 and 10000"
            raise ValueError(msg)
        return parsed

    @field_validator(
        "telegram_raw_days",
        "crawl_content_days",
        "llm_payload_days",
        "video_transcript_days",
        "interaction_text_days",
        "request_content_days",
        mode="before",
    )
    @classmethod
    def _validate_ttl_days(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        parsed = int(str(value)) if value not in (None, "") else default
        if parsed < 0:
            msg = f"{info.field_name} must be >= 0 (0 means 'never purge')"
            raise ValueError(msg)
        return parsed
