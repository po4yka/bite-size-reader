from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class RedisConfig(BaseModel):
    """Shared Redis connection settings."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")
    cache_enabled: bool = Field(default=True, validation_alias="REDIS_CACHE_ENABLED")
    required: bool = Field(
        default=False,
        validation_alias="REDIS_REQUIRED",
        description="If true, fail requests when Redis is unavailable.",
    )
    url: str | None = Field(default=None, validation_alias="REDIS_URL")
    host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: str | None = Field(default=None, validation_alias="REDIS_PASSWORD")
    prefix: str = Field(default="bsr", validation_alias="REDIS_PREFIX")
    socket_timeout: float = Field(default=5.0, validation_alias="REDIS_SOCKET_TIMEOUT")
    cache_timeout_sec: float = Field(default=0.3, validation_alias="REDIS_CACHE_TIMEOUT_SEC")
    firecrawl_ttl_seconds: int = Field(
        default=21_600, validation_alias="REDIS_FIRECRAWL_TTL_SECONDS"
    )
    llm_ttl_seconds: int = Field(default=7_200, validation_alias="REDIS_LLM_TTL_SECONDS")

    @field_validator("url", mode="before")
    @classmethod
    def _normalize_url(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        cleaned = str(value).strip()
        if cleaned and len(cleaned) > 200:
            msg = "Redis URL appears too long"
            raise ValueError(msg)
        return cleaned

    @field_validator("host", mode="before")
    @classmethod
    def _validate_host(cls, value: Any) -> str:
        host = str(value or "").strip()
        if not host:
            msg = "Redis host is required when URL is not provided"
            raise ValueError(msg)
        if len(host) > 200:
            msg = "Redis host appears too long"
            raise ValueError(msg)
        return host

    @field_validator("port", "db", mode="before")
    @classmethod
    def _validate_int_bounds(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        limits: dict[str, tuple[int, int]] = {
            "port": (0, 65535),
            "db": (0, 65535),
            "firecrawl_ttl_seconds": (60, 86_400 * 14),
            "llm_ttl_seconds": (60, 86_400 * 14),
        }
        min_val, max_val = limits.get(info.field_name, (0, 65535))
        if parsed < min_val or parsed > max_val:
            msg = (
                f"{info.field_name.replace('_', ' ').capitalize()} must be between "
                f"{min_val} and {max_val}"
            )
            raise ValueError(msg)
        return parsed

    @field_validator("socket_timeout", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> float:
        default = cls.model_fields["socket_timeout"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Redis socket timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 60:
            msg = "Redis socket timeout must be between 0 and 60 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("cache_timeout_sec", mode="before")
    @classmethod
    def _validate_cache_timeout(cls, value: Any) -> float:
        default = cls.model_fields["cache_timeout_sec"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Redis cache timeout must be a valid number"
            raise ValueError(msg) from exc
        if parsed <= 0 or parsed > 5:
            msg = "Redis cache timeout must be between 0 and 5 seconds"
            raise ValueError(msg)
        return parsed

    @field_validator("prefix", mode="before")
    @classmethod
    def _validate_prefix(cls, value: Any) -> str:
        prefix = str(value or "bsr").strip()
        if not prefix:
            msg = "Redis prefix cannot be empty"
            raise ValueError(msg)
        if len(prefix) > 50:
            msg = "Redis prefix appears too long"
            raise ValueError(msg)
        if any(ch in prefix for ch in (" ", "\t", "\n", "\r")):
            msg = "Redis prefix cannot contain whitespace"
            raise ValueError(msg)
        return prefix
