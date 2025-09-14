from __future__ import annotations

import os
from dataclasses import dataclass

# ruff: noqa: E501


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    fallback_models: tuple[str, ...]
    http_referer: str | None
    x_title: str | None
    max_tokens: int | None = None
    top_p: float | None = None
    temperature: float = 0.2
    provider_order: tuple[str, ...] = ()
    enable_stats: bool = False


@dataclass(frozen=True)
class FirecrawlConfig:
    api_key: str


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int
    api_hash: str
    bot_token: str
    allowed_user_ids: tuple[int, ...]


@dataclass(frozen=True)
class RuntimeConfig:
    db_path: str
    log_level: str
    request_timeout_sec: int
    preferred_lang: str
    debug_payloads: bool
    enable_textacy: bool = False
    enable_chunking: bool = False
    chunk_max_chars: int = 200000


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    runtime: RuntimeConfig


def _parse_allowed_user_ids(value: str | None) -> tuple[int, ...]:
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Parsing ALLOWED_USER_IDS: {value}")
    if not value:
        return tuple()
    ids: list[int] = []
    for piece in value.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            ids.append(int(piece))
        except ValueError:
            continue
    logger.info(f"Parsed IDs: {ids}")
    return tuple(ids)


def _validate_api_key(api_key: str, name: str) -> str:
    """Validate API key format and security."""
    if not api_key:
        raise ValueError(f"{name} API key is required")
    if len(api_key) < 10:
        raise ValueError(f"{name} API key appears to be too short")
    if len(api_key) > 500:
        raise ValueError(f"{name} API key appears to be too long")
    # Basic security: no obvious secrets in logs
    if any(char in api_key for char in [" ", "\n", "\t"]):
        raise ValueError(f"{name} API key contains invalid characters")
    return api_key


def _validate_bot_token(bot_token: str) -> str:
    """Validate Telegram bot token format."""
    if not bot_token:
        raise ValueError("Bot token is required")
    # Telegram bot tokens have format: numbers:letters
    if ":" not in bot_token:
        raise ValueError("Bot token format appears invalid")
    parts = bot_token.split(":")
    if len(parts) != 2:
        raise ValueError("Bot token format appears invalid")
    if not parts[0].isdigit():
        raise ValueError("Bot token ID part appears invalid")
    if len(parts[1]) < 30:
        raise ValueError("Bot token secret part appears too short")
    return bot_token


def _validate_api_id(api_id: str) -> int:
    """Validate Telegram API ID."""
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0:
            raise ValueError("API ID must be positive")
        if api_id_int > 2**31 - 1:  # SQLite INTEGER limit
            raise ValueError("API ID too large")
        return api_id_int
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError("API ID must be a valid integer") from e
        raise


def _validate_timeout(timeout_str: str) -> int:
    """Validate timeout value."""
    try:
        timeout = int(timeout_str)
        if timeout <= 0:
            raise ValueError("Timeout must be positive")
        if timeout > 3600:  # 1 hour max
            raise ValueError("Timeout too large (max 3600 seconds)")
        return timeout
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError("Timeout must be a valid integer") from e
        raise


def _validate_log_level(log_level: str) -> str:
    """Validate log level."""
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if log_level.upper() not in valid_levels:
        raise ValueError(f"Invalid log level: {log_level}. Must be one of {valid_levels}")
    return log_level.upper()


def _validate_lang(lang: str) -> str:
    """Validate language preference."""
    valid_langs = {"auto", "en", "ru"}
    if lang not in valid_langs:
        raise ValueError(f"Invalid language: {lang}. Must be one of {valid_langs}")
    return lang


def _validate_max_tokens(max_tokens_str: str | None) -> int | None:
    """Validate max_tokens parameter."""
    if not max_tokens_str:
        return None
    try:
        max_tokens = int(max_tokens_str)
        if max_tokens <= 0:
            raise ValueError("Max tokens must be positive")
        if max_tokens > 100000:  # Reasonable upper limit
            raise ValueError("Max tokens too large")
        return max_tokens
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError("Max tokens must be a valid integer") from e
        raise


def _validate_top_p(top_p_str: str | None) -> float | None:
    """Validate top_p parameter."""
    if not top_p_str:
        return None
    try:
        top_p = float(top_p_str)
        if top_p < 0 or top_p > 1:
            raise ValueError("Top_p must be between 0 and 1")
        return top_p
    except ValueError as e:
        if "could not convert" in str(e):
            raise ValueError("Top_p must be a valid number") from e
        raise


def _validate_temperature(temp_str: str | None) -> float:
    """Validate temperature parameter."""
    if not temp_str:
        return 0.2  # Default value
    try:
        temperature = float(temp_str)
        if temperature < 0 or temperature > 2:
            raise ValueError("Temperature must be between 0 and 2")
        return temperature
    except ValueError as e:
        if "could not convert" in str(e):
            raise ValueError("Temperature must be a valid number") from e
        raise


def _validate_model_name(model: str) -> str:
    """Validate model name for security and allow OpenRouter-style IDs.

    OpenRouter models commonly use identifiers like:
      - "openai/gpt-4o-mini"
      - "anthropic/claude-3.5-sonnet:beta"
      - "meta-llama/llama-3.1-8b-instruct:free"

    We therefore allow a conservative set of characters found in such names:
    letters, digits, dash, underscore, dot, forward slash and colon.
    """
    if not model:
        raise ValueError("Model name cannot be empty")
    if len(model) > 100:
        raise ValueError("Model name too long")

    # Disallow path traversal or obvious injection markers
    if ".." in model or "<" in model or ">" in model or "\\" in model:
        raise ValueError("Model name contains invalid characters")

    # Allowlist characters typical for OpenRouter model IDs
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
    if any(ch not in allowed for ch in model):
        raise ValueError("Model name contains invalid characters")
    return model


def _validate_fallback_models(fallback_raw: str) -> tuple[str, ...]:
    """Validate fallback models list."""
    if not fallback_raw:
        return tuple()

    models = []
    for model in fallback_raw.split(","):
        model = model.strip()
        if model:
            try:
                validated_model = _validate_model_name(model)
                models.append(validated_model)
            except ValueError:
                # Skip invalid models rather than failing completely
                continue
    return tuple(models)


def _parse_provider_order(order_raw: str | None) -> tuple[str, ...]:
    if not order_raw:
        return tuple()
    out: list[str] = []
    for piece in order_raw.split(","):
        slug = piece.strip()
        if not slug:
            continue
        # conservative validation: allow letters, numbers, dash and colon
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-:")
        if any(ch not in allowed for ch in slug):
            continue
        if len(slug) <= 100:
            out.append(slug)
    return tuple(out)


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Required values:
    - API_ID, API_HASH, BOT_TOKEN
    - FIRECRAWL_API_KEY
    - OPENROUTER_API_KEY

    Optional values have sensible defaults based on SPEC.md.
    """
    try:
        telegram = TelegramConfig(
            api_id=_validate_api_id(os.getenv("API_ID", "0")),
            api_hash=_validate_api_key(os.getenv("API_HASH", ""), "API Hash"),
            bot_token=_validate_bot_token(os.getenv("BOT_TOKEN", "")),
            allowed_user_ids=_parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS")),
        )

        firecrawl = FirecrawlConfig(
            api_key=_validate_api_key(os.getenv("FIRECRAWL_API_KEY", ""), "Firecrawl")
        )

        fallback_models = _validate_fallback_models(os.getenv("OPENROUTER_FALLBACK_MODELS", ""))

        openrouter = OpenRouterConfig(
            api_key=_validate_api_key(os.getenv("OPENROUTER_API_KEY", ""), "OpenRouter"),
            model=_validate_model_name(os.getenv("OPENROUTER_MODEL", "openai/gpt-5")),
            fallback_models=fallback_models,
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER"),
            x_title=os.getenv("OPENROUTER_X_TITLE"),
            max_tokens=_validate_max_tokens(os.getenv("OPENROUTER_MAX_TOKENS")),
            top_p=_validate_top_p(os.getenv("OPENROUTER_TOP_P")),
            temperature=_validate_temperature(os.getenv("OPENROUTER_TEMPERATURE")),
            provider_order=_parse_provider_order(os.getenv("OPENROUTER_PROVIDER_ORDER")),
            enable_stats=os.getenv("OPENROUTER_ENABLE_STATS", "0").lower() in ("1", "true", "yes"),
        )

        runtime = RuntimeConfig(
            db_path=os.getenv("DB_PATH", "/data/app.db"),
            log_level=_validate_log_level(os.getenv("LOG_LEVEL", "INFO")),
            request_timeout_sec=_validate_timeout(os.getenv("REQUEST_TIMEOUT_SEC", "60")),
            preferred_lang=_validate_lang(os.getenv("PREFERRED_LANG", "auto")),
            debug_payloads=os.getenv("DEBUG_PAYLOADS", "0").lower() in ("1", "true"),
            enable_textacy=os.getenv("TEXTACY_ENABLED", "0").lower() in ("1", "true", "yes"),
            enable_chunking=os.getenv("CHUNKING_ENABLED", "0").lower() in ("1", "true", "yes"),
            chunk_max_chars=int(os.getenv("CHUNK_MAX_CHARS", "200000")),
        )

        return AppConfig(
            telegram=telegram, firecrawl=firecrawl, openrouter=openrouter, runtime=runtime
        )
    except Exception as e:
        raise RuntimeError(f"Configuration validation failed: {e}") from e
