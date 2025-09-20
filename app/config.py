from __future__ import annotations

import logging
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
    long_context_model: str | None = None
    # Structured output settings
    enable_structured_outputs: bool = True
    structured_output_mode: str = "json_schema"  # "json_schema" or "json_object"
    require_parameters: bool = True  # Prefer providers that support all parameters
    auto_fallback_structured: bool = True  # Auto-fallback to json_object if json_schema fails


@dataclass(frozen=True)
class FirecrawlConfig:
    api_key: str
    # Connection pooling settings
    max_connections: int = 10
    max_keepalive_connections: int = 5
    keepalive_expiry: float = 30.0
    # Retry configuration
    retry_max_attempts: int = 3
    retry_initial_delay: float = 1.0
    retry_max_delay: float = 10.0
    retry_backoff_factor: float = 2.0
    # Credit monitoring
    credit_warning_threshold: int = 1000
    credit_critical_threshold: int = 100


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
    log_truncate_length: int = 1000


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


def _validate_structured_output_mode(mode_str: str | None) -> str:
    """Validate structured output mode."""
    if not mode_str:
        return "json_schema"  # Default to most capable mode
    valid_modes = {"json_schema", "json_object"}
    if mode_str not in valid_modes:
        raise ValueError(
            f"Invalid structured output mode: {mode_str}. Must be one of {valid_modes}"
        )
    return mode_str


def _validate_connection_pool_param_int(
    value_str: str | None, param_name: str, min_val: int, max_val: int, default: int
) -> int:
    """Validate connection pool parameter that should be an int."""
    if not value_str:
        return default
    try:
        value = int(value_str)
        if value < min_val or value > max_val:
            raise ValueError(f"{param_name} must be between {min_val} and {max_val}")
        return value
    except ValueError as e:
        if "could not convert" in str(e) or "invalid literal" in str(e):
            raise ValueError(f"{param_name} must be a valid integer") from e
        raise


def _validate_connection_pool_param_float(
    value_str: str | None, param_name: str, min_val: float, max_val: float, default: float
) -> float:
    """Validate connection pool parameter that should be a float."""
    if not value_str:
        return default
    try:
        value = float(value_str)
        if value < min_val or value > max_val:
            raise ValueError(f"{param_name} must be between {min_val} and {max_val}")
        return value
    except ValueError as e:
        if "could not convert" in str(e) or "invalid literal" in str(e):
            raise ValueError(f"{param_name} must be a valid number") from e
        raise


def _validate_model_name(model: str) -> str:
    """Validate model name for security and allow OpenRouter-style IDs.

    OpenRouter models commonly use identifiers like:
      - "openai/gpt-4o-mini"
      - "openai/gpt-5"
      - "google/gemini-2.5-pro"

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


logger = logging.getLogger(__name__)


def load_config(*, allow_stub_telegram: bool = False) -> AppConfig:
    """Load configuration from environment variables.

    Required values:
    - API_ID, API_HASH, BOT_TOKEN
    - FIRECRAWL_API_KEY
    - OPENROUTER_API_KEY

    Optional values have sensible defaults based on SPEC.md.
    When ``allow_stub_telegram`` is True, placeholder Telegram credentials are
    generated if the related environment variables are absent. This is useful
    for local CLI tooling where the Telegram client is not started.
    """
    try:
        api_id_raw = os.getenv("API_ID")
        api_hash_raw = os.getenv("API_HASH")
        bot_token_raw = os.getenv("BOT_TOKEN")

        using_stub_telegram = False
        if allow_stub_telegram:
            if not api_id_raw:
                api_id_raw = "1"
                using_stub_telegram = True
            if not api_hash_raw:
                api_hash_raw = "test_api_hash_placeholder_value___"
                using_stub_telegram = True
            if not bot_token_raw:
                bot_token_raw = "1000000000:TESTTOKENPLACEHOLDER1234567890ABC"
                using_stub_telegram = True

        telegram = TelegramConfig(
            api_id=_validate_api_id(api_id_raw or "0"),
            api_hash=_validate_api_key(api_hash_raw or "", "API Hash"),
            bot_token=_validate_bot_token(bot_token_raw or ""),
            allowed_user_ids=_parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS")),
        )

        if using_stub_telegram:
            logger.warning(
                "Using stub Telegram credentials: real API_ID/API_HASH/BOT_TOKEN were not provided"
            )

        firecrawl = FirecrawlConfig(
            api_key=_validate_api_key(os.getenv("FIRECRAWL_API_KEY", ""), "Firecrawl"),
            max_connections=_validate_connection_pool_param_int(
                os.getenv("FIRECRAWL_MAX_CONNECTIONS"), "Max connections", 1, 100, 10
            ),
            max_keepalive_connections=_validate_connection_pool_param_int(
                os.getenv("FIRECRAWL_MAX_KEEPALIVE_CONNECTIONS"),
                "Max keepalive connections",
                1,
                50,
                5,
            ),
            keepalive_expiry=_validate_connection_pool_param_float(
                os.getenv("FIRECRAWL_KEEPALIVE_EXPIRY"), "Keepalive expiry", 1.0, 300.0, 30.0
            ),
            retry_max_attempts=_validate_connection_pool_param_int(
                os.getenv("FIRECRAWL_RETRY_MAX_ATTEMPTS"), "Retry max attempts", 0, 10, 3
            ),
            retry_initial_delay=_validate_connection_pool_param_float(
                os.getenv("FIRECRAWL_RETRY_INITIAL_DELAY"), "Retry initial delay", 0.1, 60.0, 1.0
            ),
            retry_max_delay=_validate_connection_pool_param_float(
                os.getenv("FIRECRAWL_RETRY_MAX_DELAY"), "Retry max delay", 1.0, 300.0, 10.0
            ),
            retry_backoff_factor=_validate_connection_pool_param_float(
                os.getenv("FIRECRAWL_RETRY_BACKOFF_FACTOR"), "Retry backoff factor", 1.0, 10.0, 2.0
            ),
            credit_warning_threshold=_validate_connection_pool_param_int(
                os.getenv("FIRECRAWL_CREDIT_WARNING_THRESHOLD"),
                "Credit warning threshold",
                1,
                10000,
                1000,
            ),
            credit_critical_threshold=_validate_connection_pool_param_int(
                os.getenv("FIRECRAWL_CREDIT_CRITICAL_THRESHOLD"),
                "Credit critical threshold",
                1,
                1000,
                100,
            ),
        )

        fallback_models = _validate_fallback_models(os.getenv("OPENROUTER_FALLBACK_MODELS", ""))

        openrouter = OpenRouterConfig(
            api_key=_validate_api_key(os.getenv("OPENROUTER_API_KEY", ""), "OpenRouter"),
            # Default to a broadly available model. GPT-5 may require specific provider routing.
            model=_validate_model_name(os.getenv("OPENROUTER_MODEL", "openai/gpt-5")),
            fallback_models=fallback_models,
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER"),
            x_title=os.getenv("OPENROUTER_X_TITLE"),
            max_tokens=_validate_max_tokens(os.getenv("OPENROUTER_MAX_TOKENS")),
            top_p=_validate_top_p(os.getenv("OPENROUTER_TOP_P")),
            temperature=_validate_temperature(os.getenv("OPENROUTER_TEMPERATURE")),
            provider_order=_parse_provider_order(os.getenv("OPENROUTER_PROVIDER_ORDER")),
            enable_stats=os.getenv("OPENROUTER_ENABLE_STATS", "0").lower() in ("1", "true", "yes"),
            long_context_model=(
                _validate_model_name(os.getenv("OPENROUTER_LONG_CONTEXT_MODEL", ""))
                if os.getenv("OPENROUTER_LONG_CONTEXT_MODEL")
                else None
            ),
            # Structured output configuration
            enable_structured_outputs=os.getenv("OPENROUTER_ENABLE_STRUCTURED_OUTPUTS", "1").lower()
            in ("1", "true", "yes"),
            structured_output_mode=_validate_structured_output_mode(
                os.getenv("OPENROUTER_STRUCTURED_OUTPUT_MODE")
            ),
            require_parameters=os.getenv("OPENROUTER_REQUIRE_PARAMETERS", "1").lower()
            in ("1", "true", "yes"),
            auto_fallback_structured=os.getenv("OPENROUTER_AUTO_FALLBACK_STRUCTURED", "1").lower()
            in ("1", "true", "yes"),
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
            log_truncate_length=int(os.getenv("LOG_TRUNCATE_LENGTH", "1000")),
        )

        return AppConfig(
            telegram=telegram, firecrawl=firecrawl, openrouter=openrouter, runtime=runtime
        )
    except Exception as e:
        raise RuntimeError(f"Configuration validation failed: {e}") from e
