from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from app.di.types import SchedulerDependencies

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


def build_scheduler_dependencies(
    cfg: AppConfig,
    db: DatabaseSessionManager,
) -> SchedulerDependencies:
    """Build scheduler job factories without constructing jobs inline in the service."""
    return SchedulerDependencies(
        karakeep_service_factory=lambda: _create_karakeep_service(cfg, db),
        karakeep_user_id_resolver=lambda: _resolve_default_user_id(cfg),
        digest_userbot_factory=lambda: _create_digest_userbot(cfg),
        digest_llm_factory=lambda: _create_digest_llm_client(cfg),
        digest_bot_client_factory=lambda: _create_digest_bot_client(cfg),
        digest_service_factory=lambda userbot, llm_client, send_message: _create_digest_service(
            cfg,
            userbot=userbot,
            llm_client=llm_client,
            send_message=send_message,
        ),
    )


def _resolve_default_user_id(cfg: AppConfig) -> int | None:
    return cfg.telegram.allowed_user_ids[0] if cfg.telegram.allowed_user_ids else None


def _create_karakeep_service(cfg: AppConfig, db: DatabaseSessionManager) -> Any:
    from app.adapters.karakeep import KarakeepSyncService
    from app.di.repositories import build_karakeep_sync_repository

    karakeep_repo = build_karakeep_sync_repository(db)
    return KarakeepSyncService(
        api_url=cfg.karakeep.api_url,
        api_key=cfg.karakeep.api_key,
        sync_tag=cfg.karakeep.sync_tag,
        repository=cast("Any", karakeep_repo),
    )


def _create_digest_userbot(cfg: AppConfig) -> Any:
    from app.adapters.digest.userbot_client import UserbotClient

    return UserbotClient(cfg, Path("/data"))


def _create_digest_llm_client(cfg: AppConfig) -> Any:
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

    return OpenRouterClient(
        api_key=cfg.openrouter.api_key,
        model=cfg.openrouter.model,
        fallback_models=cfg.openrouter.fallback_models,
    )


def _create_digest_bot_client(cfg: AppConfig) -> Any:
    from pyrogram import Client as PyroClient

    return PyroClient(
        name="digest_bot_sender",
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
        bot_token=cfg.telegram.bot_token,
        in_memory=True,
    )


def _create_digest_service(
    cfg: AppConfig,
    *,
    userbot: Any,
    llm_client: Any,
    send_message: Callable[[int, str, Any | None], Awaitable[None]],
) -> Any:
    from app.adapters.digest.analyzer import DigestAnalyzer
    from app.adapters.digest.channel_reader import ChannelReader
    from app.adapters.digest.digest_service import DigestService
    from app.adapters.digest.formatter import DigestFormatter

    reader = ChannelReader(cfg, userbot)
    analyzer = DigestAnalyzer(cfg, llm_client)
    formatter = DigestFormatter()
    return DigestService(
        cfg=cfg,
        reader=reader,
        analyzer=analyzer,
        formatter=formatter,
        send_message_func=send_message,
    )
