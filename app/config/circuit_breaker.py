from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for external services."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="CIRCUIT_BREAKER_ENABLED",
        description="Enable circuit breaker for external service calls",
    )
    failure_threshold: int = Field(
        default=5,
        validation_alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD",
        description="Number of failures before opening circuit",
    )
    timeout_seconds: float = Field(
        default=60.0,
        validation_alias="CIRCUIT_BREAKER_TIMEOUT_SECONDS",
        description="Seconds to wait before entering half-open state",
    )
    success_threshold: int = Field(
        default=2,
        validation_alias="CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
        description="Successful attempts needed in half-open to close",
    )

    @field_validator("failure_threshold", "success_threshold", mode="before")
    @classmethod
    def _validate_threshold(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        try:
            parsed = float(str(value if value not in (None, "") else 60.0))
        except ValueError as exc:
            msg = "Circuit breaker timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 1.0 or parsed > 600.0:
            msg = "Circuit breaker timeout must be between 1 and 600 seconds"
            raise ValueError(msg)
        return parsed
