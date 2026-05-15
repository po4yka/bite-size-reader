"""Retention policy configuration for raw artifact purge."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
