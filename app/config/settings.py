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

from ._validators import _parse_allowed_user_ids
from .api import ApiLimitsConfig, AuthConfig, SyncConfig
from .async_jobs import BackgroundProcessorConfig
from .content import ContentLimitsConfig, FirecrawlConfig
from .infrastructure import (
    ChromaConfig,
    CircuitBreakerConfig,
    DatabaseConfig,
    McpConfig,
    RedisConfig,
)
from .integrations import KarakeepConfig, WebSearchConfig, YouTubeConfig
from .llm import AnthropicConfig, OpenAIConfig, OpenRouterConfig
from .telegram import TelegramConfig, TelegramLimitsConfig

logger = logging.getLogger(__name__)


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
    summary_prompt_version: str = Field(default="v1", validation_alias="SUMMARY_PROMPT_VERSION")
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
    llm_provider: str = Field(default="openrouter", validation_alias="LLM_PROVIDER")

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _validate_llm_provider(cls, value: Any) -> str:
        provider = str(value or "openrouter").lower().strip()
        valid_providers = {"openrouter", "openai", "anthropic"}
        if provider not in valid_providers:
            msg = f"Invalid LLM provider: {provider}. Must be one of {sorted(valid_providers)}"
            raise ValueError(msg)
        return provider

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

    @field_validator("summary_prompt_version", mode="before")
    @classmethod
    def _validate_prompt_version(cls, value: Any) -> str:
        raw = str(value or "v1").strip()
        if not raw:
            msg = "Summary prompt version cannot be empty"
            raise ValueError(msg)
        if len(raw) > 30:
            msg = "Summary prompt version is too long"
            raise ValueError(msg)
        if any(ch.isspace() for ch in raw):
            msg = "Summary prompt version cannot contain whitespace"
            raise ValueError(msg)
        return raw

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
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    youtube: YouTubeConfig
    runtime: RuntimeConfig
    telegram_limits: TelegramLimitsConfig
    database: DatabaseConfig
    content_limits: ContentLimitsConfig
    vector_store: ChromaConfig
    redis: RedisConfig
    api_limits: ApiLimitsConfig
    auth: AuthConfig
    sync: SyncConfig
    background: BackgroundProcessorConfig
    karakeep: KarakeepConfig
    circuit_breaker: CircuitBreakerConfig
    web_search: WebSearchConfig


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
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    youtube: YouTubeConfig = Field(default_factory=YouTubeConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    telegram_limits: TelegramLimitsConfig = Field(default_factory=TelegramLimitsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    content_limits: ContentLimitsConfig = Field(default_factory=ContentLimitsConfig)
    vector_store: ChromaConfig = Field(default_factory=ChromaConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    api_limits: ApiLimitsConfig = Field(default_factory=ApiLimitsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    background: BackgroundProcessorConfig = Field(default_factory=BackgroundProcessorConfig)
    karakeep: KarakeepConfig = Field(default_factory=KarakeepConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)

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
            openai=self.openai,
            anthropic=self.anthropic,
            youtube=self.youtube,
            runtime=self.runtime,
            telegram_limits=self.telegram_limits,
            database=self.database,
            content_limits=self.content_limits,
            vector_store=self.vector_store,
            redis=self.redis,
            api_limits=self.api_limits,
            auth=self.auth,
            sync=self.sync,
            background=self.background,
            karakeep=self.karakeep,
            circuit_breaker=self.circuit_breaker,
            web_search=self.web_search,
        )


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
