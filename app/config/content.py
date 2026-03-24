from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContentLimitsConfig(BaseModel):
    """Content processing limits configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    max_text_length_kb: int = Field(
        default=50,
        validation_alias="MAX_TEXT_LENGTH_KB",
        description="Maximum text length in kilobytes (for URL extraction, regex DoS prevention)",
    )

    content_quality_llm_enabled: bool = Field(
        default=False,
        validation_alias="CONTENT_QUALITY_LLM_ENABLED",
        description="Enable LLM-based content quality classification for ambiguous cases",
    )
    content_quality_llm_timeout_sec: float = Field(
        default=3.0,
        validation_alias="CONTENT_QUALITY_LLM_TIMEOUT_SEC",
        description="Timeout in seconds for LLM content quality check",
    )
    content_quality_llm_confidence_threshold: float = Field(
        default=0.7,
        validation_alias="CONTENT_QUALITY_LLM_CONFIDENCE_THRESHOLD",
        description="Minimum LLM confidence to override heuristic verdict",
    )

    @field_validator("max_text_length_kb", mode="before")
    @classmethod
    def _validate_text_length(cls, value: Any) -> int:
        if value in (None, ""):
            return 50
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Max text length must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Max text length must be positive"
            raise ValueError(msg)
        if parsed > 1024:
            msg = "Max text length must be 1024 KB or less"
            raise ValueError(msg)
        return parsed
