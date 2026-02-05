from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class DatabaseConfig(BaseModel):
    """Database operation limits and timeouts configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    operation_timeout: float = Field(
        default=30.0,
        validation_alias="DB_OPERATION_TIMEOUT",
        description="Database operation timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        validation_alias="DB_MAX_RETRIES",
        description="Maximum retries for transient database errors",
    )
    json_max_size: int = Field(
        default=10_000_000,
        validation_alias="DB_JSON_MAX_SIZE",
        description="Maximum JSON payload size in bytes (10MB)",
    )
    json_max_depth: int = Field(
        default=20,
        validation_alias="DB_JSON_MAX_DEPTH",
        description="Maximum JSON nesting depth",
    )
    json_max_array_length: int = Field(
        default=10_000,
        validation_alias="DB_JSON_MAX_ARRAY_LENGTH",
        description="Maximum JSON array length",
    )
    json_max_dict_keys: int = Field(
        default=1_000,
        validation_alias="DB_JSON_MAX_DICT_KEYS",
        description="Maximum JSON dictionary keys",
    )

    @field_validator("operation_timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        if value in (None, ""):
            return 30.0
        try:
            parsed = float(str(value))
        except ValueError as exc:
            msg = "Database operation timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Database operation timeout must be positive"
            raise ValueError(msg)
        if parsed > 3600:
            msg = "Database operation timeout must be 3600 seconds or less"
            raise ValueError(msg)
        return parsed

    @field_validator(
        "max_retries",
        "json_max_size",
        "json_max_depth",
        "json_max_array_length",
        "json_max_dict_keys",
        mode="before",
    )
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            return int(default)
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be positive"
            raise ValueError(msg)
        return parsed
