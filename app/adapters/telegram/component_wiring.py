"""Dependency wiring helpers for Telegram bot composition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.repository_ports import create_batch_session_repository

if TYPE_CHECKING:
    from app.adapters.telegram.bot_factory import BotComponents
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


class TelegramComponentWiring:
    """Applies wiring and patching rules for Telegram bot components."""

    def __init__(self, *, cfg: AppConfig, db: DatabaseSessionManager) -> None:
        self._cfg = cfg
        self._db = db

    def apply_client_shims(
        self,
        *,
        telegram_client_module: Any,
        client_cls: Any,
        filters_obj: Any,
    ) -> None:
        """Route runtime/test pyrogram shims into telegram client module."""
        setattr(telegram_client_module, "Client", client_cls)  # noqa: B010
        setattr(telegram_client_module, "filters", filters_obj)  # noqa: B010
        if client_cls is object:
            telegram_client_module.PYROGRAM_AVAILABLE = False

    def bind_runtime_components(
        self,
        *,
        bot: Any,
        components: BotComponents,
        llm_client: Any,
    ) -> None:
        """Assign components to bot and wire cross-component dependencies."""
        bot.telegram_client = components.telegram_client
        bot.response_formatter = components.response_formatter
        bot.url_processor = components.url_processor
        bot.forward_processor = components.forward_processor
        bot.message_handler = components.message_handler
        bot.topic_searcher = components.topic_searcher
        bot.local_searcher = components.local_searcher
        bot.embedding_service = components.embedding_service
        bot.vector_search_service = components.chroma_vector_search_service
        bot.query_expansion_service = components.query_expansion_service
        bot.hybrid_search_service = components.hybrid_search_service
        bot.vector_store = components.vector_store
        bot._container = components.container

        bot.message_handler.command_processor.url_processor = bot.url_processor
        bot.message_handler.url_handler.url_processor = bot.url_processor
        bot.message_handler.url_processor = bot.url_processor

        bot._batch_session_repo = create_batch_session_repository(self._db)
        bot.message_handler.url_handler._llm_client = llm_client
        bot.message_handler.url_handler._batch_session_repo = bot._batch_session_repo
        bot.message_handler.url_handler._batch_config = self._cfg.batch_analysis

        bot._awaiting_url_users = bot.message_handler.url_handler._awaiting_url_users
