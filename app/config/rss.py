"""RSS feed configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RSSConfig(BaseModel):
    """Configuration for the RSS feed subscription and auto-summarization subsystem."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=False, validation_alias="RSS_ENABLED")
    poll_interval_minutes: int = Field(
        default=30,
        validation_alias="RSS_POLL_INTERVAL_MINUTES",
        ge=5,
        le=1440,
        description="How often to poll feeds (minutes)",
    )
    auto_summarize: bool = Field(
        default=True,
        validation_alias="RSS_AUTO_SUMMARIZE",
        description="Automatically summarize and deliver new items",
    )
    min_content_length: int = Field(
        default=500,
        validation_alias="RSS_MIN_CONTENT_LENGTH",
        ge=0,
        le=10000,
        description="Min chars in RSS content to use inline (skip scraping)",
    )
    max_items_per_poll: int = Field(
        default=20,
        validation_alias="RSS_MAX_ITEMS_PER_POLL",
        ge=1,
        le=100,
        description="Safety cap on items processed per poll cycle",
    )
    concurrency: int = Field(
        default=2,
        validation_alias="RSS_CONCURRENCY",
        ge=1,
        le=10,
        description="Parallel LLM summarization calls",
    )
