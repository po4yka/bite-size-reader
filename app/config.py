from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

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

# ruff: noqa: E501


def validate_model_name(model: str) -> str:
    """Validate model name for security and allow OpenRouter-style IDs."""

    if not model:
        raise ValueError("Model name cannot be empty")
    if len(model) > 100:
        raise ValueError("Model name too long")

    if ".." in model or "<" in model or ">" in model or "\\" in model:
        raise ValueError("Model name contains invalid characters")

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
    if any(ch not in allowed for ch in model):
        raise ValueError("Model name contains invalid characters")

    return model


def _ensure_api_key(value: str, *, name: str) -> str:
    if not value:
        raise ValueError(f"{name} API key is required")
    value = value.strip()
    if not value:
        raise ValueError(f"{name} API key is required")
    if len(value) > 500:
        raise ValueError(f"{name} API key appears to be too long")
    if any(char in value for char in [" ", "\n", "\t"]):
        raise ValueError(f"{name} API key contains invalid characters")
    return value


def _parse_allowed_user_ids(value: Any) -> tuple[int, ...]:
    if value in (None, ""):
        return tuple()
    if isinstance(value, list | tuple):
        values = value
    else:
        values = str(value).split(",")

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
            raise ValueError("API ID is required")
        else:
            try:
                api_id = int(str(value))
            except ValueError as exc:  # pragma: no cover - defensive
                raise ValueError("API ID must be a valid integer") from exc

        if api_id < 0:
            raise ValueError("API ID must be non-negative")
        if api_id > 2**31 - 1:
            raise ValueError("API ID too large")
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
            raise ValueError("Bot token format appears invalid")
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError("Bot token format appears invalid")
        if not parts[0].isdigit():
            raise ValueError("Bot token ID part appears invalid")
        if len(parts[1]) < 30:
            raise ValueError("Bot token secret part appears too short")
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
        mode="before",
    )
    @classmethod
    def _parse_int_bounds(cls, value: Any, info: ValidationInfo) -> int:
        if value in (None, ""):
            default = cls.model_fields[info.field_name].default
            if default is None:
                raise ValueError(f"{info.field_name.replace('_', ' ')} is required")
            return int(default)
        try:
            parsed = int(str(value))
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"{info.field_name.replace('_', ' ')} must be a valid integer"
            ) from exc

        limits: dict[str, tuple[int, int]] = {
            "max_connections": (1, 100),
            "max_keepalive_connections": (1, 50),
            "retry_max_attempts": (0, 10),
            "credit_warning_threshold": (1, 10000),
            "credit_critical_threshold": (1, 1000),
        }
        min_val, max_val = limits[info.field_name]
        if parsed < min_val or parsed > max_val:
            raise ValueError(
                f"{info.field_name.replace('_', ' ').capitalize()} must be between {min_val} and {max_val}"
            )
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
                raise ValueError(f"{info.field_name.replace('_', ' ')} is required")
            return float(default)
        try:
            parsed = float(str(value))
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{info.field_name.replace('_', ' ')} must be a valid number") from exc

        limits: dict[str, tuple[float, float]] = {
            "keepalive_expiry": (1.0, 300.0),
            "retry_initial_delay": (0.1, 60.0),
            "retry_max_delay": (1.0, 300.0),
            "retry_backoff_factor": (1.0, 10.0),
        }
        min_val, max_val = limits[info.field_name]
        if parsed < min_val or parsed > max_val:
            raise ValueError(
                f"{info.field_name.replace('_', ' ').capitalize()} must be between {min_val} and {max_val}"
            )
        return parsed


class OpenRouterConfig(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    model: str = Field(default="openai/gpt-5", validation_alias="OPENROUTER_MODEL")
    fallback_models: tuple[str, ...] = Field(
        default_factory=tuple, validation_alias="OPENROUTER_FALLBACK_MODELS"
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
        default=None, validation_alias="OPENROUTER_LONG_CONTEXT_MODEL"
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
            return tuple()
        if isinstance(value, list | tuple):
            iterable = value
        else:
            iterable = str(value).split(",")

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
            raise ValueError("Max tokens must be a valid integer") from exc
        if tokens <= 0:
            raise ValueError("Max tokens must be positive")
        if tokens > 100000:
            raise ValueError("Max tokens too large")
        return tokens

    @field_validator("top_p", mode="before")
    @classmethod
    def _validate_top_p(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            top_p = float(str(value))
        except ValueError as exc:
            raise ValueError("Top_p must be a valid number") from exc
        if top_p < 0 or top_p > 1:
            raise ValueError("Top_p must be between 0 and 1")
        return top_p

    @field_validator("temperature", mode="before")
    @classmethod
    def _validate_temperature(cls, value: Any) -> float:
        if value in (None, ""):
            return 0.2
        try:
            temperature = float(str(value))
        except ValueError as exc:
            raise ValueError("Temperature must be a valid number") from exc
        if temperature < 0 or temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")
        return temperature

    @field_validator("structured_output_mode", mode="before")
    @classmethod
    def _validate_structured_output_mode(cls, value: Any) -> str:
        if value in (None, ""):
            return "json_schema"
        mode_value = str(value)
        if mode_value not in {"json_schema", "json_object"}:
            raise ValueError(
                f"Invalid structured output mode: {mode_value}. Must be one of {{'json_schema', 'json_object'}}"
            )
        return mode_value

    @field_validator("provider_order", mode="before")
    @classmethod
    def _parse_provider_order(cls, value: Any) -> tuple[str, ...]:
        if value in (None, ""):
            return tuple()
        if isinstance(value, list | tuple):
            iterable = value
        else:
            iterable = str(value).split(",")

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
    db_backup_enabled: bool = Field(default=True, validation_alias="DB_BACKUP_ENABLED")
    db_backup_interval_minutes: int = Field(
        default=360, validation_alias="DB_BACKUP_INTERVAL_MINUTES"
    )
    db_backup_retention: int = Field(default=14, validation_alias="DB_BACKUP_RETENTION")
    db_backup_dir: str | None = Field(default=None, validation_alias="DB_BACKUP_DIR")

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, value: Any) -> str:
        log_level = str(value or "INFO").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            raise ValueError(f"Invalid log level: {value}. Must be one of {valid_levels}")
        return log_level

    @field_validator("request_timeout_sec", mode="before")
    @classmethod
    def _validate_timeout(cls, value: Any) -> int:
        try:
            timeout = int(str(value or 60))
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError("Timeout must be a valid integer") from exc
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        if timeout > 3600:
            raise ValueError("Timeout too large (max 3600 seconds)")
        return timeout

    @field_validator("preferred_lang", mode="before")
    @classmethod
    def _validate_lang(cls, value: Any) -> str:
        lang = str(value or "auto")
        if lang not in {"auto", "en", "ru"}:
            raise ValueError(f"Invalid language: {lang}. Must be one of {{'auto', 'en', 'ru'}}")
        return lang

    @field_validator("chunk_max_chars", "log_truncate_length", mode="before")
    @classmethod
    def _validate_positive_int(cls, value: Any, info: ValidationInfo) -> int:
        default = cls.model_fields[info.field_name].default
        try:
            parsed = int(str(value if value not in (None, "") else default))
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"{info.field_name.replace('_', ' ')} must be a valid integer"
            ) from exc
        if parsed <= 0:
            raise ValueError(f"{info.field_name.replace('_', ' ').capitalize()} must be positive")
        return parsed

    @field_validator("db_backup_interval_minutes", mode="before")
    @classmethod
    def _validate_backup_interval(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 360))
        except ValueError as exc:
            raise ValueError("DB backup interval (minutes) must be a valid integer") from exc
        if parsed < 5 or parsed > 10080:
            raise ValueError("DB backup interval (minutes) must be between 5 and 10080")
        return parsed

    @field_validator("db_backup_retention", mode="before")
    @classmethod
    def _validate_backup_retention(cls, value: Any) -> int:
        try:
            parsed = int(str(value or 14))
        except ValueError as exc:
            raise ValueError("DB backup retention must be a valid integer") from exc
        if parsed < 0 or parsed > 1000:
            raise ValueError("DB backup retention must be between 0 and 1000")
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
            raise ValueError("DB backup directory contains invalid characters")
        return trimmed


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    runtime: RuntimeConfig


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    allow_stub_telegram: bool = Field(default=False, exclude=True)
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)

    @classmethod
    def _load_flattened_environment(cls, env: Mapping[str, str]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_name, field in cls.model_fields.items():
            if field_name == "allow_stub_telegram":
                continue
            annotation = field.annotation
            if not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
                continue

            nested_values: dict[str, Any] = {}
            nested_model: type[BaseModel] = annotation
            for nested_name, nested_field in nested_model.model_fields.items():
                value = cls._resolve_env_value(env, nested_field)
                if value is not None:
                    nested_values[nested_name] = value
            if nested_values:
                data[field_name] = nested_values
        return data

    @staticmethod
    def _resolve_env_value(env: Mapping[str, str], field: Any) -> Any | None:
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
            if name in env:
                return env[name]
        return None

    @model_validator(mode="after")
    def _ensure_allowed_users(self) -> Self:
        if not self.allow_stub_telegram and not self.telegram.allowed_user_ids:
            raise RuntimeError(
                "ALLOWED_USER_IDS must contain at least one Telegram user ID; "
                "set the environment variable to a comma-separated list."
            )
        return self

    def as_app_config(self) -> AppConfig:
        return AppConfig(
            telegram=self.telegram,
            firecrawl=self.firecrawl,
            openrouter=self.openrouter,
            runtime=self.runtime,
        )


logger = logging.getLogger(__name__)


def load_config(*, allow_stub_telegram: bool = False) -> AppConfig:
    overrides: dict[str, Any] = {}
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
        env_data = Settings._load_flattened_environment(os.environ)
        merged: dict[str, Any] = _deep_merge(env_data, overrides)
        merged["allow_stub_telegram"] = allow_stub_telegram
        settings = Settings(**merged)
    except (ValidationError, RuntimeError) as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Configuration validation failed: {exc}") from exc

    if using_stub_telegram:
        logger.warning(
            "Using stub Telegram credentials: real API_ID/API_HASH/BOT_TOKEN were not provided"
        )

    return settings.as_app_config()


def _deep_merge(base: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    if not updates:
        return dict(base)

    result: dict[str, Any] = {k: v for k, v in base.items()}
    for key, value in updates.items():
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
