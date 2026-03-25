from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from typing import Self

from pydantic import AliasChoices, BaseModel, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ._validators import _parse_allowed_user_ids
from .adaptive_timeout import AdaptiveTimeoutConfig
from .api import ApiLimitsConfig, AuthConfig, SyncConfig
from .background import BackgroundProcessorConfig
from .circuit_breaker import CircuitBreakerConfig
from .content import ContentLimitsConfig
from .database import DatabaseConfig
from .digest import ChannelDigestConfig
from .firecrawl import FirecrawlConfig  # noqa: TC001
from .integrations import (
    BatchAnalysisConfig,
    ChromaConfig,
    EmbeddingConfig,
    McpConfig,
    WebSearchConfig,
)
from .llm import AnthropicConfig, ModelRoutingConfig, OpenAIConfig, OpenRouterConfig
from .media import AttachmentConfig, YouTubeConfig
from .push import PushNotificationConfig
from .redis import RedisConfig
from .rss import RSSConfig
from .runtime import RuntimeConfig
from .scraper import ScraperConfig
from .telegram import TelegramConfig, TelegramLimitsConfig
from .tts import ElevenLabsConfig
from .twitter import TwitterConfig

logger = get_logger(__name__)
_CONFIG_CACHE_LOCK = threading.Lock()
_CONFIG_CACHE: dict[bool, AppConfig] = {}

_DEPRECATED_SCRAPER_ENV_RENAMES = {
    "SCRAPLING_ENABLED": "SCRAPER_SCRAPLING_ENABLED",
    "SCRAPLING_TIMEOUT_SEC": "SCRAPER_SCRAPLING_TIMEOUT_SEC",
    "SCRAPLING_STEALTH_FALLBACK": "SCRAPER_SCRAPLING_STEALTH_FALLBACK",
    "SCRAPER_DIRECT_HTTP_ENABLED": "SCRAPER_DIRECT_HTML_ENABLED",
}


def raise_on_deprecated_scraper_env_vars() -> None:
    present: dict[str, str] = {}
    for old_name, new_name in _DEPRECATED_SCRAPER_ENV_RENAMES.items():
        if old_name in os.environ:
            present[old_name] = new_name

    env_file_path = Path(".env")
    if env_file_path.exists():
        for line in env_file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in _DEPRECATED_SCRAPER_ENV_RENAMES:
                present[key] = _DEPRECATED_SCRAPER_ENV_RENAMES[key]

    if not present:
        return

    details = "; ".join(f"{old} -> {new}" for old, new in sorted(present.items()))
    msg = f"Deprecated scraper environment variables detected. Use the new names only: {details}"
    raise RuntimeError(msg)


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    youtube: YouTubeConfig
    attachment: AttachmentConfig
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
    circuit_breaker: CircuitBreakerConfig
    web_search: WebSearchConfig
    adaptive_timeout: AdaptiveTimeoutConfig
    batch_analysis: BatchAnalysisConfig
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    digest: ChannelDigestConfig = field(default_factory=ChannelDigestConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    tts: ElevenLabsConfig = field(default_factory=ElevenLabsConfig)
    push: PushNotificationConfig = field(default_factory=PushNotificationConfig)
    model_routing: ModelRoutingConfig = field(default_factory=ModelRoutingConfig)
    rss: RSSConfig = field(default_factory=RSSConfig)


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
    attachment: AttachmentConfig = Field(default_factory=AttachmentConfig)
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
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    web_search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    adaptive_timeout: AdaptiveTimeoutConfig = Field(default_factory=AdaptiveTimeoutConfig)
    batch_analysis: BatchAnalysisConfig = Field(default_factory=BatchAnalysisConfig)
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    digest: ChannelDigestConfig = Field(default_factory=ChannelDigestConfig)
    scraper: ScraperConfig = Field(default_factory=ScraperConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    tts: ElevenLabsConfig = Field(default_factory=ElevenLabsConfig)
    push: PushNotificationConfig = Field(default_factory=PushNotificationConfig)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    rss: RSSConfig = Field(default_factory=RSSConfig)

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

        # Load YAML model config (lowest priority layer)
        from app.config.models_file import load_models_yaml

        yaml_data = load_models_yaml()

        # Merge: YAML < .env / constructor args < os.environ
        # ``data`` includes .env file values loaded by pydantic-settings, so
        # os.environ must come last to preserve the standard precedence
        # (env vars override .env file).
        env_data: dict[str, Any] = dict(os.environ)
        merged_source = {**yaml_data, **data, **env_data}
        cls._fail_on_deprecated_scraper_envs(merged_source)

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
    def _fail_on_deprecated_scraper_envs(source: dict[str, Any]) -> None:
        deprecated: list[str] = []
        for old_name, new_name in _DEPRECATED_SCRAPER_ENV_RENAMES.items():
            if old_name in source:
                deprecated.append(f"{old_name} -> {new_name}")
        if not deprecated:
            return
        msg = (
            "Deprecated scraper environment variables detected. "
            "Use the new names only: " + "; ".join(deprecated)
        )
        raise RuntimeError(msg)

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
            attachment=self.attachment,
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
            circuit_breaker=self.circuit_breaker,
            web_search=self.web_search,
            adaptive_timeout=self.adaptive_timeout,
            batch_analysis=self.batch_analysis,
            twitter=self.twitter,
            digest=self.digest,
            mcp=self.mcp,
            scraper=self.scraper,
            embedding=self.embedding,
            tts=self.tts,
            push=self.push,
            model_routing=self.model_routing,
            rss=self.rss,
        )


def clear_config_cache() -> None:
    """Clear cached AppConfig instances.

    Tests mutate environment variables between runs, so they need a way to
    invalidate the process-level config cache.
    """
    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE.clear()


def _build_config(*, allow_stub_telegram: bool) -> AppConfig:
    """Build a fresh immutable AppConfig from environment variables."""
    overrides: dict[str, Any] = {"allow_stub_telegram": allow_stub_telegram}
    using_stub_telegram = False
    raise_on_deprecated_scraper_env_vars()

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
        settings = Settings(**overrides)
    except (ValidationError, RuntimeError) as exc:  # pragma: no cover - defensive
        msg = f"Configuration validation failed: {exc}"
        raise RuntimeError(msg) from exc

    if using_stub_telegram:
        logger.warning(
            "Using stub Telegram credentials: real API_ID/API_HASH/BOT_TOKEN were not provided"
        )

    return settings.as_app_config()


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
    with _CONFIG_CACHE_LOCK:
        cached = _CONFIG_CACHE.get(allow_stub_telegram)
        if cached is not None:
            return cached

        config = _build_config(allow_stub_telegram=allow_stub_telegram)
        _CONFIG_CACHE[allow_stub_telegram] = config
        return config


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
    def is_user_allowed(user_id: int, *, fail_open_when_empty: bool = False) -> bool:
        """Check if user_id is in the ALLOWED_USER_IDS whitelist.

        When the whitelist is empty, behavior is governed by fail_open_when_empty:
        - True: allow all users (permissive — suitable for optional whitelist paths)
        - False: deny all users (strict — suitable for high-security auth paths)
        """
        allowed_ids = Config.get_allowed_user_ids()
        if not allowed_ids:
            return fail_open_when_empty
        return user_id in allowed_ids

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
