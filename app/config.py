from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    fallback_models: tuple[str, ...]
    http_referer: str | None
    x_title: str | None


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


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    firecrawl: FirecrawlConfig
    openrouter: OpenRouterConfig
    runtime: RuntimeConfig


def _parse_allowed_user_ids(value: str | None) -> tuple[int, ...]:
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
    return tuple(ids)


def load_config() -> AppConfig:
    """Load configuration from environment variables.

    Required values:
    - API_ID, API_HASH, BOT_TOKEN
    - FIRECRAWL_API_KEY
    - OPENROUTER_API_KEY

    Optional values have sensible defaults based on SPEC.md.
    """
    telegram = TelegramConfig(
        api_id=int(os.getenv("API_ID", "0")),
        api_hash=os.getenv("API_HASH", ""),
        bot_token=os.getenv("BOT_TOKEN", ""),
        allowed_user_ids=_parse_allowed_user_ids(os.getenv("ALLOWED_USER_IDS")),
    )

    firecrawl = FirecrawlConfig(api_key=os.getenv("FIRECRAWL_API_KEY", ""))

    fallback_raw = os.getenv("OPENROUTER_FALLBACK_MODELS", "")
    fallback_models = tuple(m.strip() for m in fallback_raw.split(",") if m.strip())

    openrouter = OpenRouterConfig(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        model=os.getenv("OPENROUTER_MODEL", "openai/gpt-5"),
        fallback_models=fallback_models,
        http_referer=os.getenv("OPENROUTER_HTTP_REFERER"),
        x_title=os.getenv("OPENROUTER_X_TITLE"),
    )

    runtime = RuntimeConfig(
        db_path=os.getenv("DB_PATH", "/data/app.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        request_timeout_sec=int(os.getenv("REQUEST_TIMEOUT_SEC", "60")),
    )

    return AppConfig(
        telegram=telegram, firecrawl=firecrawl, openrouter=openrouter, runtime=runtime
    )
