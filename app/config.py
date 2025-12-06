from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def validate_model_name(model: str) -> str:
    """Validate model name for security and allow OpenRouter-style IDs."""
    if not model:
        msg = "Model name cannot be empty"
        raise ValueError(msg)
    if len(model) > 100:
        msg = "Model name too long"
        raise ValueError(msg)

    if ".." in model or "<" in model or ">" in model or "\\" in model:
        msg = "Model name contains invalid characters"
        raise ValueError(msg)

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
    if any(ch not in allowed for ch in model):
        msg = "Model name contains invalid characters"
        raise ValueError(msg)

    return model


def _ensure_api_key(value: str, *, name: str) -> str:
    if not value:
        msg = f"{name} API key is required"
        raise ValueError(msg)
    value = value.strip()
    if not value:
        msg = f"{name} API key is required"
        raise ValueError(msg)
    if len(value) > 500:
        msg = f"{name} API key appears to be too long"
        raise ValueError(msg)
    if any(char in value for char in [" ", "\n", "\t"]):
        msg = f"{name} API key contains invalid characters"
        raise ValueError(msg)
    return value


def _parse_allowed_user_ids(value: Any) -> tuple[int, ...]:
    if value in (None, ""):
        return ()
    values = value if isinstance(value, list | tuple) else str(value).split(",")

    user_ids: list[int] = []
    for piece in values:
        piece = str(piece).strip()
        if not piece:
            continue
        try:
            user_ids.append(int(piece))
        except ValueError:
            continue
    return tuple(user_ids)


class TelegramConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_id: int = Field(
        ...,
        validation_alias=AliasChoices("API_ID", "TELEGRAM_API_ID"),
        description="Telegram API ID",
    )
    api_hash: str = Field(
        ...,
        validation_alias=AliasChoices("API_HASH", "TELEGRAM_API_HASH"),
        description="Telegram API hash",
    )
    bot_token: str = Field(
        ...,
        validation_alias=AliasChoices("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        description="Telegram bot token",
    )
    allowed_user_ids: tuple[int, ...] = Field(
        default_factory=tuple,
        validation_alias=AliasChoices("ALLOWED_USER_IDS", "TELEGRAM_ALLOWED_USER_IDS"),
        description="Comma separated list of Telegram user IDs that may interact with the bot",
    )

    @field_validator("api_id", mode="before")
    @classmethod
    def _parse_api_id(cls, value: Any) -> int:
        if isinstance(value, int):
            api_id = value
        elif value is None or value == "":
            msg = "API ID is required"
            raise ValueError(msg)
        else:
            try:
                api_id = int(str(value))
            except ValueError as exc:  # pragma: no cover - defensive
                msg = "API ID must be a valid integer"
                raise ValueError(msg) from exc

        if api_id < 0:
            msg = "API ID must be non-negative"
            raise ValueError(msg)
        if api_id > 2**31 - 1:
            msg = "API ID too large"
            raise ValueError(msg)
        return api_id

    @field_validator("api_hash", mode="before")
    @classmethod
    def _validate_api_hash(cls, value: Any) -> str:
        api_hash = str(value or "")
        if not api_hash:
            return ""
        return _ensure_api_key(api_hash, name="API Hash")

    @field_validator("bot_token", mode="before")
    @classmethod
    def _validate_bot_token(cls, value: Any) -> str:
        token = str(value or "")
        if not token:
            return ""
        if ":" not in token:
            msg = "Bot token format appears invalid"
            raise ValueError(msg)
        parts = token.split(":")
        if len(parts) != 2:
            msg = "Bot token format appears invalid"
            raise ValueError(msg)
        if not parts[0].isdigit():
            msg = "Bot token ID part appears invalid"
            raise ValueError(msg)
        if len(parts[1]) < 30:
            msg = "Bot token secret part appears too short"
            raise ValueError(msg)
        return token

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _parse_allowed_users(cls, value: Any) -> tuple[int, ...]:
        return _parse_allowed_user_ids(value)


class FirecrawlConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(..., validation_alias="FIRECRAWL_API_KEY", description="Firecrawl API key")
    max_connections: int = Field(default=10, validation_alias="FIRECRAWL_MAX_CONNECTIONS")
    max_keepalive_connections: int = Field(
        default=5, validation_alias="FIRECRAWL_MAX_KEEPALIVE_CONNECTIONS"
    )
    keepalive_expiry: float = Field(default=30.0, validation_alias="FIRECRAWL_KEEPALIVE_EXPIRY")
    retry_max_attempts: int = Field(default=3, validation_alias="FIRECRAWL_RETRY_MAX_ATTEMPTS")
    retry_initial_delay: float = Field(
        default=1.0, validation_alias="FIRECRAWL_RETRY_INITIAL_DELAY"
    )
    retry_max_delay: float = Field(default=10.0, validation_alias="FIRECRAWL_RETRY_MAX_DELAY")
    retry_backoff_factor: float = Field(
        default=2.0, validation_alias="FIRECRAWL_RETRY_BACKOFF_FACTOR"
    )
    credit_warning_threshold: int = Field(
        default=1000, validation_alias="FIRECRAWL_CREDIT_WARNING_THRESHOLD"
    )
    credit_critical_threshold: int = Field(
        default=100, validation_alias="FIRECRAWL_CREDIT_CRITICAL_THRESHOLD"
    )
    max_response_size_mb: int = Field(default=50, validation_alias="FIRECRAWL_MAX_RESPONSE_SIZE_MB")

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        return _ensure_api_key(str(value or ""), name="Firecrawl")

    @field_validator(
        "max_connections",
        "max_keepalive_connections",
        "retry_max_attempts",
        "credit_warning_threshold",
        "credit_critical_threshold",
        "max_response_size_mb",
        mode="before",
    )
    @classmethod
    def _parse_int_bounds(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            if default is None:
                msg = f"{info.field_name.replace('_', ' ')} is required"
                raise ValueError(msg)
            return int(default)
        try:
            parsed = int(str(value))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc

        limits: dict[str, tuple[int, int]] = {
            "max_connections": (1, 100),
            "max_keepalive_connections": (1, 50),
            "retry_max_attempts": (0, 10),
            "credit_warning_threshold": (1, 10000),
            "credit_critical_threshold": (1, 1000),
            "max_response_size_mb": (1, 1024),
        }
        min_val, max_val = limits[info.field_name]
        if parsed < min_val or parsed > max_val:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between {min_val} and {max_val}"
            raise ValueError(msg)
        return parsed

    @field_validator(
        "keepalive_expiry",
        "retry_initial_delay",
        "retry_max_delay",
        "retry_backoff_factor",
        mode="before",
    )
    @classmethod
    def _parse_float_bounds(cls, value: Any, info: ValidationInfo) -> float:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            if default is None:
                msg = f"{info.field_name.replace('_', ' ')} is required"
                raise ValueError(msg)
            return float(default)
        try:
            parsed = float(str(value))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid number"
            raise ValueError(msg) from exc

        limits: dict[str, tuple[float, float]] = {
            "keepalive_expiry": (1.0, 300.0),
            "retry_initial_delay": (0.1, 60.0),
            "retry_max_delay": (1.0, 300.0),
            "retry_backoff_factor": (1.0, 10.0),
        }
        min_val, max_val = limits[info.field_name]
        if parsed < min_val or parsed > max_val:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between {min_val} and {max_val}"
            raise ValueError(msg)
        return parsed


class OpenRouterConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    model: str = Field(default="qwen/qwen3-max", validation_alias="OPENROUTER_MODEL")
    fallback_models: tuple[str, ...] = Field(
        default_factory=lambda: (
            "deepseek/deepseek-r1",
            "moonshotai/kimi-k2-thinking",
            "deepseek/deepseek-v3.2",
        ),
        validation_alias="OPENROUTER_FALLBACK_MODELS",
    )
    http_referer: str | None = Field(default=None, validation_alias="OPENROUTER_HTTP_REFERER")
    x_title: str | None = Field(default=None, validation_alias="OPENROUTER_X_TITLE")
    max_tokens: int | None = Field(default=None, validation_alias="OPENROUTER_MAX_TOKENS")
    top_p: float | None = Field(default=None, validation_alias="OPENROUTER_TOP_P")
    temperature: float = Field(default=0.2, validation_alias="OPENROUTER_TEMPERATURE")
    provider_order: tuple[str, ...] = Field(
        default_factory=tuple, validation_alias="OPENROUTER_PROVIDER_ORDER"
    )
    enable_stats: bool = Field(default=False, validation_alias="OPENROUTER_ENABLE_STATS")
    long_context_model: str | None = Field(
        default="moonshotai/kimi-k2-thinking", validation_alias="OPENROUTER_LONG_CONTEXT_MODEL"
    )
    enable_structured_outputs: bool = Field(
        default=True, validation_alias="OPENROUTER_ENABLE_STRUCTURED_OUTPUTS"
    )
    structured_output_mode: str = Field(
        default="json_schema", validation_alias="OPENROUTER_STRUCTURED_OUTPUT_MODE"
    )
    require_parameters: bool = Field(default=True, validation_alias="OPENROUTER_REQUIRE_PARAMETERS")
    auto_fallback_structured: bool = Field(
        default=True, validation_alias="OPENROUTER_AUTO_FALLBACK_STRUCTURED"
    )
    max_response_size_mb: int = Field(
        default=10, validation_alias="OPENROUTER_MAX_RESPONSE_SIZE_MB"
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, value: Any) -> str:
        return _ensure_api_key(str(value or ""), name="OpenRouter")

    @field_validator("model", mode="before")
    @classmethod
    def _validate_model(cls, value: Any) -> str:
        return validate_model_name(str(value or ""))

    @field_validator("fallback_models", mode="before")
    @classmethod
    def _parse_fallback_models(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        validated: list[str] = []
        for raw in iterable:
            candidate = str(raw).strip()
            if not candidate:
                continue
            try:
                validated.append(validate_model_name(candidate))
            except ValueError:
                continue
        return tuple(validated)

    @field_validator("long_context_model", mode="before")
    @classmethod
    def _validate_long_context_model(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return validate_model_name(str(value))

    @field_validator("max_tokens", mode="before")
    @classmethod
    def _validate_max_tokens(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            tokens = int(str(value))
        except ValueError as exc:
            msg = "Max tokens must be a valid integer"
            raise ValueError(msg) from exc
        if tokens <= 0:
            msg = "Max tokens must be positive"
            raise ValueError(msg)
        if tokens > 100000:
            msg = "Max tokens too large"
            raise ValueError(msg)
        return tokens

    @field_validator("top_p", mode="before")
    @classmethod
    def _validate_top_p(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            top_p = float(str(value))
        except ValueError as exc:
            msg = "Top_p must be a valid number"
            raise ValueError(msg) from exc
        if top_p < 0 or top_p > 1:
            msg = "Top_p must be between 0 and 1"
            raise ValueError(msg)
        return top_p

    @field_validator("temperature", mode="before")
    @classmethod
    def _validate_temperature(cls, value: Any) -> float:
        if value in (None, ""):
            return 0.2
        try:
            temperature = float(str(value))
        except ValueError as exc:
            msg = "Temperature must be a valid number"
            raise ValueError(msg) from exc
        if temperature < 0 or temperature > 2:
            msg = "Temperature must be between 0 and 2"
            raise ValueError(msg)
        return temperature

    @field_validator("structured_output_mode", mode="before")
    @classmethod
    def _validate_structured_output_mode(cls, value: Any) -> str:
        if value in (None, ""):
            return "json_schema"
        mode_value = str(value)
        if mode_value not in {"json_schema", "json_object"}:
            msg = f"Invalid structured output mode: {mode_value}. Must be one of {{'json_schema', 'json_object'}}"
            raise ValueError(msg)
        return mode_value

    @field_validator("provider_order", mode="before")
    @classmethod
    def _parse_provider_order(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        iterable = value if isinstance(value, list | tuple) else str(value).split(",")

        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:")
        parsed: list[str] = []
        for raw in iterable:
            slug = str(raw).strip()
            if not slug or len(slug) > 100:
                continue
            if any(ch not in allowed for ch in slug):
                continue
            parsed.append(slug)
        return tuple(parsed)

    @field_validator("max_response_size_mb", mode="before")
    @classmethod
    def _validate_max_response_size_mb(cls, value: Any) -> int:
        if value in (None, ""):
            return 10
        try:
            size_mb = int(str(value))
        except ValueError as exc:
            msg = "Max response size must be a valid integer"
            raise ValueError(msg) from exc
        if size_mb < 1 or size_mb > 100:
            msg = "Max response size must be between 1 and 100 MB"
            raise ValueError(msg)
        return size_mb


class YouTubeConfig(BaseModel):
    """YouTube video download and storage configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(
        default=True,
        validation_alias="YOUTUBE_DOWNLOAD_ENABLED",
        description="Enable YouTube video downloading",
    )

    storage_path: str = Field(
        default="/data/videos",
        validation_alias="YOUTUBE_STORAGE_PATH",
        description="Path to store downloaded videos",
    )

    max_video_size_mb: int = Field(
        default=500,
        validation_alias="YOUTUBE_MAX_VIDEO_SIZE_MB",
        description="Maximum video file size in MB",
    )

    max_storage_gb: int = Field(
        default=100,
        validation_alias="YOUTUBE_MAX_STORAGE_GB",
        description="Maximum total storage for videos in GB",
    )

    auto_cleanup_enabled: bool = Field(
        default=True,
        validation_alias="YOUTUBE_AUTO_CLEANUP_ENABLED",
        description="Enable automatic cleanup of old videos",
    )

    cleanup_after_days: int = Field(
        default=30,
        validation_alias="YOUTUBE_CLEANUP_AFTER_DAYS",
        description="Delete videos older than this many days",
    )

    preferred_quality: str = Field(
        default="1080p",
        validation_alias="YOUTUBE_PREFERRED_QUALITY",
        description="Preferred video quality (1080p, 720p, 480p)",
    )

    subtitle_languages: list[str] = Field(
        default=["en", "ru"],
        validation_alias="YOUTUBE_SUBTITLE_LANGUAGES",
        description="Preferred subtitle languages (fallback order)",
    )

    @field_validator("subtitle_languages", mode="before")
    @classmethod
    def _parse_subtitle_languages(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [lang.strip() for lang in value.split(",") if lang.strip()]
        return ["en", "ru"]

    @field_validator("max_video_size_mb", "max_storage_gb", "cleanup_after_days", mode="before")
    @classmethod
    def _parse_int_fields(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            return int(default)
        try:
            return int(str(value))
        except ValueError as exc:
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc


class TelegramLimitsConfig(BaseModel):
    """Telegram message and URL limits configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    max_message_chars: int = Field(
        default=3500,
        validation_alias="TELEGRAM_MAX_MESSAGE_CHARS",
        description="Maximum characters per Telegram message (Telegram limit ~4096, keep safety margin)",
    )
    max_url_length: int = Field(
        default=2048,
        validation_alias="TELEGRAM_MAX_URL_LENGTH",
        description="Maximum URL length (RFC 2616 limit)",
    )
    max_batch_urls: int = Field(
        default=200,
        validation_alias="TELEGRAM_MAX_BATCH_URLS",
        description="Maximum number of URLs in a batch operation",
    )
    min_message_interval_ms: int = Field(
        default=100,
        validation_alias="TELEGRAM_MIN_MESSAGE_INTERVAL_MS",
        description="Minimum interval between messages in milliseconds (rate limiting)",
    )

    @field_validator("max_message_chars", "max_url_length", "max_batch_urls", mode="before")
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

    @field_validator("min_message_interval_ms", mode="before")
    @classmethod
    def _validate_message_interval(cls, value: Any) -> int:
        if value in (None, ""):
            return 100
        try:
            parsed = int(str(value))
        except ValueError as exc:
            msg = "Message interval must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0:
            msg = "Message interval must be non-negative"
            raise ValueError(msg)
        if parsed > 10000:
            msg = "Message interval must be 10000ms or less"
            raise ValueError(msg)
        return parsed


class RedisConfig(BaseModel):
    """Shared Redis connection settings."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")
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
        if parsed < 0 or parsed > 65535:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be between 0 and 65535"
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


class BackgroundProcessorConfig(BaseModel):
    """Background processor settings."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    redis_lock_enabled: bool = Field(default=True, validation_alias="BACKGROUND_REDIS_LOCK_ENABLED")
    redis_lock_required: bool = Field(
        default=False,
        validation_alias="BACKGROUND_REDIS_LOCK_REQUIRED",
        description="If true, fail processing when Redis is unavailable.",
    )
    lock_ttl_ms: int = Field(default=300_000, validation_alias="BACKGROUND_LOCK_TTL_MS")
    lock_skip_on_held: bool = Field(default=True, validation_alias="BACKGROUND_LOCK_SKIP_ON_HELD")
    retry_attempts: int = Field(default=3, validation_alias="BACKGROUND_RETRY_ATTEMPTS")
    retry_base_delay_ms: int = Field(default=500, validation_alias="BACKGROUND_RETRY_BASE_DELAY_MS")
    retry_max_delay_ms: int = Field(default=5_000, validation_alias="BACKGROUND_RETRY_MAX_DELAY_MS")
    retry_jitter_ratio: float = Field(default=0.2, validation_alias="BACKGROUND_RETRY_JITTER_RATIO")

    @field_validator("lock_ttl_ms", "retry_attempts", "retry_base_delay_ms", "retry_max_delay_ms")
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        limits: dict[str, tuple[int, int]] = {
            "lock_ttl_ms": (1_000, 3_600_000),
            "retry_attempts": (1, 10),
            "retry_base_delay_ms": (50, 60_000),
            "retry_max_delay_ms": (100, 300_000),
        }
        min_val, max_val = limits.get(info.field_name, (1, 3_600_000))
        if parsed < min_val or parsed > max_val:
            msg = (
                f"{info.field_name.replace('_', ' ').capitalize()} must be between "
                f"{min_val} and {max_val}"
            )
            raise ValueError(msg)
        return parsed

    @field_validator("retry_jitter_ratio", mode="before")
    @classmethod
    def _validate_jitter(cls, value: Any) -> float:
        default = cls.model_fields["retry_jitter_ratio"].default
        try:
            parsed = float(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Background retry jitter ratio must be a valid number"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 1:
            msg = "Background retry jitter ratio must be between 0 and 1"
            raise ValueError(msg)
        return parsed


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


class ChromaConfig(BaseModel):
    """Vector store configuration for Chroma."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    host: str = Field(
        default="http://localhost:8000",
        validation_alias="CHROMA_HOST",
        description="Chroma HTTP endpoint (scheme + host)",
    )
    auth_token: str | None = Field(
        default=None,
        validation_alias="CHROMA_AUTH_TOKEN",
        description="Optional bearer token for secured Chroma deployments",
    )
    environment: str = Field(
        default="dev",
        validation_alias=AliasChoices("CHROMA_ENV", "APP_ENV", "ENVIRONMENT"),
        description="Environment label used for namespacing collections",
    )
    user_scope: str = Field(
        default="public",
        validation_alias="CHROMA_USER_SCOPE",
        description="User or tenant scope used for namespacing collections",
    )

    @field_validator("host", mode="before")
    @classmethod
    def _validate_host(cls, value: Any) -> str:
        host = str(value or "").strip()
        if not host:
            msg = "Chroma host is required"
            raise ValueError(msg)
        if len(host) > 200:
            msg = "Chroma host value appears to be too long"
            raise ValueError(msg)
        if "\x00" in host:
            msg = "Chroma host contains invalid characters"
            raise ValueError(msg)
        return host

    @field_validator("auth_token", mode="before")
    @classmethod
    def _validate_auth_token(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        token = str(value).strip()
        if len(token) > 500:
            msg = "Chroma auth token appears to be too long"
            raise ValueError(msg)
        return token

    @field_validator("environment", "user_scope", mode="before")
    @classmethod
    def _sanitize_names(cls, value: Any, info: ValidationInfo) -> str:
        raw = str(value or "").strip() or cls.model_fields[info.field_name].default
        cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if not cleaned:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} cannot be empty"
            raise ValueError(msg)
        return cleaned.lower()


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    db_path: str = Field(default="/data/app.db", validation_alias="DB_PATH")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    request_timeout_sec: int = Field(default=60, validation_alias="REQUEST_TIMEOUT_SEC")
    preferred_lang: str = Field(default="auto", validation_alias="PREFERRED_LANG")
    debug_payloads: bool = Field(default=False, validation_alias="DEBUG_PAYLOADS")
    enable_textacy: bool = Field(default=False, validation_alias="TEXTACY_ENABLED")
    enable_chunking: bool = Field(default=False, validation_alias="CHUNKING_ENABLED")
    chunk_max_chars: int = Field(default=200000, validation_alias="CHUNK_MAX_CHARS")
    log_truncate_length: int = Field(default=1000, validation_alias="LOG_TRUNCATE_LENGTH")
    topic_search_max_results: int = Field(default=5, validation_alias="TOPIC_SEARCH_MAX_RESULTS")
    max_concurrent_calls: int = Field(default=4, validation_alias="MAX_CONCURRENT_CALLS")
    jwt_secret_key: str = Field(
        default="", validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET")
    )
    db_backup_enabled: bool = Field(default=True, validation_alias="DB_BACKUP_ENABLED")
    db_backup_interval_minutes: int = Field(
        default=360, validation_alias="DB_BACKUP_INTERVAL_MINUTES"
    )
    db_backup_retention: int = Field(default=14, validation_alias="DB_BACKUP_RETENTION")
    db_backup_dir: str | None = Field(default=None, validation_alias="DB_BACKUP_DIR")
    enable_hex_container: bool = Field(default=False, validation_alias="ENABLE_HEX_CONTAINER")

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        log_level = str(value or "INFO").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            msg = f"Invalid log level: {value}. Must be one of {valid_levels}"
            raise ValueError(msg)
        return log_level

    @field_validator("request_timeout_sec", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> int:
        try:
            timeout = int(str(value or 60))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Timeout must be a valid integer"
            raise ValueError(msg) from exc
        if timeout <= 0:
            msg = "Timeout must be positive"
            raise ValueError(msg)
        if timeout > 3600:
            msg = "Timeout too large (max 3600 seconds)"
            raise ValueError(msg)
        return timeout

    @field_validator("preferred_lang", mode="before")
    @classmethod
    def _validate_lang(cls, value: Any) -> str:
        lang = str(value or "auto")
        if lang not in {"auto", "en", "ru"}:
            msg = f"Invalid language: {lang}. Must be one of {{'auto', 'en', 'ru'}}"
            raise ValueError(msg)
        return lang

    @field_validator("chunk_max_chars", "log_truncate_length", mode="before")
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = f"{info.field_name.replace('_', ' ')} must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = f"{info.field_name.replace('_', ' ').capitalize()} must be positive"
            raise ValueError(msg)
        return parsed

    @field_validator("topic_search_max_results", mode="before")
    @classmethod
    def _validate_topic_search_limit(cls, value: Any) -> int:
        default = cls.model_fields["topic_search_max_results"].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            msg = "Topic search max results must be a valid integer"
            raise ValueError(msg) from exc
        if parsed <= 0:
            msg = "Topic search max results must be positive"
            raise ValueError(msg)
        if parsed > 10:
            msg = "Topic search max results must be 10 or fewer"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_interval_minutes", mode="before")
    @classmethod
    def _validate_backup_interval(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 360))
        except ValueError as exc:
            msg = "DB backup interval (minutes) must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 5 or parsed > 10080:
            msg = "DB backup interval (minutes) must be between 5 and 10080"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_retention", mode="before")
    @classmethod
    def _validate_backup_retention(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 14))
        except ValueError as exc:
            msg = "DB backup retention must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 0 or parsed > 1000:
            msg = "DB backup retention must be between 0 and 1000"
            raise ValueError(msg)
        return parsed

    @field_validator("db_backup_dir", mode="before")
    @classmethod
    def _validate_backup_dir(cls, value: Any) -> str | None:
        if value is None:
            return None
        trimmed = str(value).strip()
        if not trimmed:
            return None
        if "\x00" in trimmed:
            msg = "DB backup directory contains invalid characters"
            raise ValueError(msg)
        return trimmed

    @field_validator("max_concurrent_calls", mode="before")
    @classmethod
    def _validate_max_concurrent_calls(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 4))
        except ValueError as exc:
            msg = "Max concurrent calls must be a valid integer"
            raise ValueError(msg) from exc
        if parsed < 1 or parsed > 100:
            msg = "Max concurrent calls must be between 1 and 100"
            raise ValueError(msg)
        return parsed

    @field_validator("jwt_secret_key", mode="before")
    @classmethod
    def _validate_jwt_secret_key(cls, value: Any) -> str:
        if value in (None, ""):
            return ""
        secret = str(value).strip()
        if len(secret) < 32:
            logger.warning(
                "JWT secret key is shorter than 32 characters - this is insecure for production"
            )
        if len(secret) > 500:
            msg = "JWT secret key appears to be too long"
            raise ValueError(msg)
        return secret


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    youtube: YouTubeConfig
    runtime: RuntimeConfig
    telegram_limits: TelegramLimitsConfig
    database: DatabaseConfig
    content_limits: ContentLimitsConfig
    vector_store: ChromaConfig
    redis: RedisConfig
    api_limits: ApiLimitsConfig
    sync: SyncConfig
    background: BackgroundProcessorConfig


class Settings(BaseSettings):
    """Application settings loaded automatically from environment variables.

    Uses pydantic-settings for automatic environment variable loading.
    Nested models are populated by matching validation_alias on each field.
    """

    model_config = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    allow_stub_telegram: bool = Field(default=False, exclude=True)
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    telegram_limits: TelegramLimitsConfig = Field(default_factory=TelegramLimitsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    content_limits: ContentLimitsConfig = Field(default_factory=ContentLimitsConfig)
    vector_store: ChromaConfig = Field(default_factory=ChromaConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    api_limits: ApiLimitsConfig = Field(default_factory=ApiLimitsConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    background: BackgroundProcessorConfig = Field(default_factory=BackgroundProcessorConfig)

    @model_validator(mode="before")
    @classmethod
    def _build_nested_from_env(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Build nested config objects from flat environment variables.

        pydantic-settings passes constructor args as data, but environment variables
        need to be read from os.environ separately for proper nested model population.
        This validator merges both sources, with constructor args taking precedence.
        """
        if not isinstance(data, dict):
            return data

        result = dict(data)

        # Merge os.environ with constructor data (constructor takes precedence)
        env_data: dict[str, Any] = dict(os.environ)
        merged_source = {**env_data, **data}

        for field_name, field_info in cls.model_fields.items():
            if field_name in ("allow_stub_telegram",):
                continue

            annotation = field_info.annotation
            if not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
                continue

            nested_data: dict[str, Any] = {}
            nested_model: type[BaseModel] = annotation

            for nested_field_name, nested_field in nested_model.model_fields.items():
                env_value = cls._resolve_env_value(merged_source, nested_field)
                if env_value is not None:
                    nested_data[nested_field_name] = env_value

            if nested_data:
                if field_name in result and isinstance(result[field_name], dict):
                    result[field_name] = {**nested_data, **result[field_name]}
                else:
                    result[field_name] = nested_data

        return result

    @staticmethod
    def _resolve_env_value(data: dict[str, Any], field: Any) -> Any | None:
        """Resolve environment variable value for a field using its aliases."""
        aliases: list[str] = []
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            for choice in alias.choices:
                if isinstance(choice, str):
                    aliases.append(choice)
        elif isinstance(alias, str):
            aliases.append(alias)
        if field.alias:
            aliases.append(field.alias)

        for name in aliases:
            if name in data:
                return data[name]
        return None

    @model_validator(mode="after")
    def _ensure_allowed_users(self) -> Self:
        if not self.allow_stub_telegram and not self.telegram.allowed_user_ids:
            msg = (
                "ALLOWED_USER_IDS must contain at least one Telegram user ID; "
                "set the environment variable to a comma-separated list."
            )
            raise RuntimeError(msg)
        return self

    def as_app_config(self) -> AppConfig:
        return AppConfig(
            telegram=self.telegram,
            firecrawl=self.firecrawl,
            openrouter=self.openrouter,
            youtube=self.youtube,
            runtime=self.runtime,
            telegram_limits=self.telegram_limits,
            database=self.database,
            content_limits=self.content_limits,
            vector_store=self.vector_store,
            redis=self.redis,
            api_limits=self.api_limits,
            sync=self.sync,
            background=self.background,
        )


logger = logging.getLogger(__name__)


def load_config(*, allow_stub_telegram: bool = False) -> AppConfig:
    """Load application configuration from environment variables.

    Uses pydantic-settings to automatically load from:
    1. Environment variables
    2. .env file (if present)

    Args:
        allow_stub_telegram: If True, use stub Telegram credentials when not provided.
                           Useful for testing and CLI tools that don't need real credentials.

    Returns:
        Immutable AppConfig instance with all configuration sections.

    Raises:
        RuntimeError: If configuration validation fails.
    """
    overrides: dict[str, Any] = {"allow_stub_telegram": allow_stub_telegram}
    using_stub_telegram = False

    if allow_stub_telegram:
        telegram_overrides: dict[str, Any] = {}
        if not os.getenv("API_ID"):
            telegram_overrides["api_id"] = "1"
            using_stub_telegram = True
        if not os.getenv("API_HASH"):
            telegram_overrides["api_hash"] = "test_api_hash_placeholder_value___"
            using_stub_telegram = True
        if not os.getenv("BOT_TOKEN"):
            telegram_overrides["bot_token"] = "1000000000:TESTTOKENPLACEHOLDER1234567890ABC"
            using_stub_telegram = True
        if telegram_overrides:
            overrides["telegram"] = telegram_overrides

    try:
        # pydantic-settings automatically loads from environment variables and .env file
        # We pass overrides for stub telegram credentials when needed
        settings = Settings(**overrides)
    except (ValidationError, RuntimeError) as exc:  # pragma: no cover - defensive
        msg = f"Configuration validation failed: {exc}"
        raise RuntimeError(msg) from exc

    if using_stub_telegram:
        logger.warning(
            "Using stub Telegram credentials: real API_ID/API_HASH/BOT_TOKEN were not provided"
        )

    return settings.as_app_config()


class ConfigHelper:
    """Helper class for accessing configuration values from environment variables."""

    @staticmethod
    def get(key: str, default: str | None = None) -> str:
        """Get configuration value from environment variable."""
        value = os.getenv(key)
        if value is None:
            if default is None:
                raise ValueError(f"Configuration key '{key}' not found and no default provided")
            return default
        return value

    @staticmethod
    def get_allowed_user_ids() -> tuple[int, ...]:
        """Get list of allowed Telegram user IDs."""
        value = os.getenv("ALLOWED_USER_IDS", "")
        return _parse_allowed_user_ids(value)

    @staticmethod
    def get_allowed_client_ids() -> tuple[str, ...]:
        """
        Get list of allowed client application IDs.

        Client IDs are arbitrary strings that identify specific client applications
        (e.g., "android-app-v1.0", "ios-app-v2.0"). Only clients with these IDs
        can authenticate and receive access tokens.

        Returns:
            Tuple of allowed client ID strings (empty tuple allows all clients)
        """
        value = os.getenv("ALLOWED_CLIENT_IDS", "")
        if value in (None, ""):
            return ()  # Empty tuple = no client restriction (backward compatible)

        # Parse comma-separated list
        client_ids = []
        for piece in value.split(","):
            piece = piece.strip()
            if not piece:
                continue
            # Validate client ID format (alphanumeric, hyphens, underscores, dots)
            if not all(c.isalnum() or c in "-_." for c in piece):
                logger.warning(
                    f"Ignoring invalid client ID format: {piece}",
                    extra={"client_id": piece},
                )
                continue
            if len(piece) > 100:
                logger.warning(
                    f"Ignoring client ID that is too long: {piece}",
                    extra={"client_id": piece, "length": len(piece)},
                )
                continue
            client_ids.append(piece)

        return tuple(client_ids)


# Singleton instance for backward compatibility
Config = ConfigHelper
