"""Configuration for the adaptive timeout system."""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class AdaptiveTimeoutConfig(BaseModel):
    """Configuration for adaptive timeout calculation based on historical latency data.

    The adaptive timeout system learns from historical latency data stored in
    CrawlResult and LLMCall tables to estimate appropriate timeouts for URL processing.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ADAPTIVE_TIMEOUT_ENABLED", "adaptive_timeout_enabled"),
        description="Enable adaptive timeout calculation based on historical data",
    )
    min_timeout_sec: float = Field(
        default=60.0,
        validation_alias=AliasChoices("ADAPTIVE_TIMEOUT_MIN_SEC", "adaptive_timeout_min_sec"),
        description="Minimum timeout in seconds (floor)",
    )
    max_timeout_sec: float = Field(
        default=600.0,
        validation_alias=AliasChoices("ADAPTIVE_TIMEOUT_MAX_SEC", "adaptive_timeout_max_sec"),
        description="Maximum timeout in seconds (cap)",
    )
    default_timeout_sec: float = Field(
        default=300.0,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_DEFAULT_SEC", "adaptive_timeout_default_sec"
        ),
        description="Default timeout when no historical data is available",
    )
    target_percentile: float = Field(
        default=0.95,
        validation_alias=AliasChoices("ADAPTIVE_TIMEOUT_PERCENTILE", "adaptive_timeout_percentile"),
        description="Target percentile for latency estimation (e.g., 0.95 for P95)",
    )
    safety_margin: float = Field(
        default=1.3,
        validation_alias=AliasChoices("ADAPTIVE_TIMEOUT_MARGIN", "adaptive_timeout_margin"),
        description="Multiplier applied to percentile estimate for safety buffer",
    )
    cache_ttl_sec: int = Field(
        default=300,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_CACHE_TTL_SEC", "adaptive_timeout_cache_ttl_sec"
        ),
        description="Time-to-live for cached latency statistics in seconds",
    )
    history_days: int = Field(
        default=7,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_HISTORY_DAYS", "adaptive_timeout_history_days"
        ),
        description="Number of days of historical data to consider",
    )
    min_samples: int = Field(
        default=10,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_MIN_SAMPLES", "adaptive_timeout_min_samples"
        ),
        description="Minimum number of samples required for confident estimates",
    )
    content_base_timeout_sec: float = Field(
        default=60.0,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_CONTENT_BASE_SEC", "adaptive_timeout_content_base_sec"
        ),
        description="Base timeout for content-length based estimation",
    )
    content_per_10k_chars_sec: float = Field(
        default=5.0,
        validation_alias=AliasChoices(
            "ADAPTIVE_TIMEOUT_CONTENT_PER_10K_SEC", "adaptive_timeout_content_per_10k_sec"
        ),
        description="Additional seconds per 10,000 characters of content",
    )

    @field_validator("enabled", mode="before")
    @classmethod
    def _validate_enabled(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    @field_validator("min_timeout_sec", "max_timeout_sec", "default_timeout_sec", mode="before")
    @classmethod
    def _validate_timeout_float(cls, value: Any) -> float:
        try:
            parsed = float(str(value))
        except (ValueError, TypeError) as exc:
            msg = "Timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Timeout must be positive"
            raise ValueError(msg)
        if parsed > 3600:
            msg = "Timeout too large (max 3600 seconds)"
            raise ValueError(msg)
        return parsed

    @field_validator("target_percentile", mode="before")
    @classmethod
    def _validate_percentile(cls, value: Any) -> float:
        try:
            parsed = float(str(value))
        except (ValueError, TypeError) as exc:
            msg = "Percentile must be a valid number"
            raise ValueError(msg) from exc
        if not 0.0 < parsed <= 1.0:
            msg = "Percentile must be between 0 and 1 (exclusive/inclusive)"
            raise ValueError(msg)
        return parsed

    @field_validator("safety_margin", mode="before")
    @classmethod
    def _validate_safety_margin(cls, value: Any) -> float:
        try:
            parsed = float(str(value))
        except (ValueError, TypeError) as exc:
            msg = "Safety margin must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 1.0:
            msg = "Safety margin must be at least 1.0"
            raise ValueError(msg)
        if parsed > 5.0:
            msg = "Safety margin too large (max 5.0)"
            raise ValueError(msg)
        return parsed

    @field_validator("cache_ttl_sec", "history_days", "min_samples", mode="before")
    @classmethod
    def _validate_positive_int(cls, value: Any) -> int:
        try:
            parsed = int(str(value))
        except (ValueError, TypeError) as exc:
            msg = "Value must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Value must be positive"
            raise ValueError(msg)
        return parsed

    @field_validator("content_base_timeout_sec", "content_per_10k_chars_sec", mode="before")
    @classmethod
    def _validate_content_timeout(cls, value: Any) -> float:
        try:
            parsed = float(str(value))
        except (ValueError, TypeError) as exc:
            msg = "Content timeout value must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0:
            msg = "Content timeout value must be non-negative"
            raise ValueError(msg)
        return parsed
