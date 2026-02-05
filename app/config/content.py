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
