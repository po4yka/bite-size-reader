from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

logger = logging.getLogger(__name__)


class ApiLimitsConfig(BaseModel):
    """API rate limiting configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    window_seconds: int = Field(default=60, validation_alias="API_RATE_LIMIT_WINDOW_SECONDS")
    cooldown_multiplier: float = Field(
        default=2.0, validation_alias="API_RATE_LIMIT_COOLDOWN_MULTIPLIER"
    )
    max_concurrent: int = Field(
        default=3, validation_alias="API_RATE_LIMIT_MAX_CONCURRENT_PER_USER"
    )
    default_limit: int = Field(default=100, validation_alias="API_RATE_LIMIT_DEFAULT")
    summaries_limit: int = Field(default=200, validation_alias="API_RATE_LIMIT_SUMMARIES")
    requests_limit: int = Field(default=10, validation_alias="API_RATE_LIMIT_REQUESTS")
    search_limit: int = Field(default=50, validation_alias="API_RATE_LIMIT_SEARCH")

    @field_validator("window_seconds", mode="before")
    @classmethod
    def _validate_window(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 60))
        except ValueError as exc:
            msg = "API rate limit window must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 3600:
            msg = "API rate limit window must be between 1 and 3600 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("cooldown_multiplier", mode="before")
    @classmethod
    def _validate_cooldown_multiplier(cls, value: Any) -> float:
        try:
            parsed = float(str(value if value not in (None, "") else 2.0))
        except ValueError as exc:
            msg = "Cooldown multiplier must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 10:
            msg = "Cooldown multiplier must be between 0 and 10"
            raise ValueError(msg)
        return parsed

    @field_validator(
        "max_concurrent",
        "default_limit",
        "summaries_limit",
        "requests_limit",
        "search_limit",
        mode="before",
    )
    @classmethod
    def _validate_limits(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 10000:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between 1 and 10000"
            raise ValueError(msg)
        return parsed


class AuthConfig(BaseModel):
    """Authentication feature configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    secret_login_enabled: bool = Field(
        default=False,
        validation_alias="SECRET_LOGIN_ENABLED",
        description="Enable alternate secret-key login flow",
    )
    secret_min_length: int = Field(
        default=32,
        validation_alias="SECRET_LOGIN_MIN_LENGTH",
        description="Minimum length for client-provided secrets",
    )
    secret_max_length: int = Field(
        default=128,
        validation_alias="SECRET_LOGIN_MAX_LENGTH",
        description="Maximum length for client-provided secrets",
    )
    secret_max_failed_attempts: int = Field(
        default=5,
        validation_alias="SECRET_LOGIN_MAX_FAILED_ATTEMPTS",
        description="Maximum failed attempts before lockout",
    )
    secret_lockout_minutes: int = Field(
        default=15,
        validation_alias="SECRET_LOGIN_LOCKOUT_MINUTES",
        description="Lockout duration after repeated failures",
    )
    secret_pepper: str | None = Field(
        default=None,
        validation_alias="SECRET_LOGIN_PEPPER",
        description="Optional pepper used when hashing secret keys",
    )

    @model_validator(mode="after")
    def _validate_lengths(self) -> AuthConfig:
        if self.secret_min_length <= 0 or self.secret_max_length <= 0:
            raise ValueError("secret lengths must be positive")
        if self.secret_min_length >= self.secret_max_length:
            raise ValueError("secret_min_length must be less than secret_max_length")
        return self

    @field_validator("secret_max_failed_attempts", mode="before")
    @classmethod
    def _validate_failed_attempts(cls, value: Any) -> int:
        default = cls.model_fields["secret_max_failed_attempts"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "secret_max_failed_attempts must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 100:
            msg = "secret_max_failed_attempts must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("secret_lockout_minutes", mode="before")
    @classmethod
    def _validate_lockout_minutes(cls, value: Any) -> int:
        default = cls.model_fields["secret_lockout_minutes"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:
            msg = "secret_lockout_minutes must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 24 * 60:
            msg = "secret_lockout_minutes must be between 1 and 1440"
            raise ValueError(msg)
        return parsed

    @field_validator("secret_min_length", "secret_max_length", mode="before")
    @classmethod
    def _validate_lengths_fields(cls, value: Any, info: ValidationInfo) -> int:
        defaults = {"secret_min_length": 32, "secret_max_length": 128}
        try:
            parsed = int(str(value if value not in (None, "") else defaults[info.field_name]))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 4096:
            msg = f"{info.field_name.replace('_', ' ')} must be between 1 and 4096"
            raise ValueError(msg)
        return parsed

    @field_validator("secret_pepper", mode="before")
    @classmethod
    def _validate_pepper(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        pepper = str(value).strip()
        if len(pepper) < 16:
            logger.warning("SECRET_LOGIN_PEPPER is shorter than 16 characters - use stronger value")
        if len(pepper) > 500:
            msg = "SECRET_LOGIN_PEPPER appears too long"
            raise ValueError(msg)
        return pepper


class SyncConfig(BaseModel):
    """Mobile sync configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    expiry_hours: int = Field(default=1, validation_alias="SYNC_EXPIRY_HOURS")
    default_limit: int = Field(default=200, validation_alias="SYNC_DEFAULT_LIMIT")
    min_limit: int = Field(default=1, validation_alias="SYNC_MIN_LIMIT")
    max_limit: int = Field(default=500, validation_alias="SYNC_MAX_LIMIT")
    target_payload_kb: int = Field(default=512, validation_alias="SYNC_TARGET_PAYLOAD_KB")

    @field_validator("expiry_hours", mode="before")
    @classmethod
    def _validate_expiry(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 1))
        except ValueError as exc:
            msg = "Sync expiry hours must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 168:
            msg = "Sync expiry hours must be between 1 and 168"
            raise ValueError(msg)
        return parsed

    @field_validator("default_limit", mode="before")
    @classmethod
    def _validate_default_limit(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 200))
        except ValueError as exc:
            msg = "Sync default limit must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 500:
            msg = "Sync default limit must be between 1 and 500"
            raise ValueError(msg)
        return parsed

    @field_validator("min_limit", "max_limit", mode="before")
    @classmethod
    def _validate_limits(cls, value: Any, info: ValidationInfo) -> int:
        defaults = {"min_limit": 1, "max_limit": 500}
        try:
            parsed = int(str(value if value not in (None, "") else defaults[info.field_name]))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 1000:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between 1 and 1000"
            raise ValueError(msg)
        return parsed

    @model_validator(mode="after")
    def _validate_ranges(self) -> SyncConfig:
        if self.min_limit > self.max_limit:
            raise ValueError("sync min_limit cannot exceed max_limit")
        if self.default_limit < self.min_limit or self.default_limit > self.max_limit:
            raise ValueError("sync default_limit must be within min_limit and max_limit")
        return self

    @field_validator("target_payload_kb", mode="before")
    @classmethod
    def _validate_target_payload(cls, value: Any) -> int:
        try:
            parsed = int(str(value if value not in (None, "") else 512))
        except ValueError as exc:
            msg = "Sync target payload size must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 64 or parsed > 4096:
            msg = "Sync target payload size must be between 64 and 4096 KB"
            raise ValueError(msg)
        return parsed
