from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

# Flag used at runtime to decide whether Telegram client is available
PYROGRAM_AVAILABLE: bool = True

if TYPE_CHECKING:
    # Type-only imports; mypy sees these, runtime won't execute
    from collections.abc import Awaitable, Callable

    from pyrogram import Client, filters  # pragma: no cover
    from pyrogram.types import Message  # pragma: no cover

    from app.config import AppConfig
else:
    try:
        # PyroTGFork (pyrogram import name) handles Python 3.13+ event loop
        # natively -- no bootstrap workaround needed (unlike pyrogram 2.0.106).
        from pyrogram import Client, filters
        from pyrogram.types import Message

        PYROGRAM_AVAILABLE = True
    except Exception:  # pragma: no cover - allow import in environments without deps
        Client = object
        filters = None
        Message = object
        PYROGRAM_AVAILABLE = False

logger = logging.getLogger(__name__)


class TelegramClient:
    """Handles Pyrogram client setup and operations."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.client: Client | None = None
        # Optional TopicManager, set externally by bot_factory when forum topics enabled
        self.topic_manager: Any = None

        # Initialize Telegram client (PyroTGFork/Pyrogram)
        if not PYROGRAM_AVAILABLE or Client is object:
            self.client = None
        else:
            self.client = Client(
                name="bite_size_reader_bot",
                api_id=self.cfg.telegram.api_id,
                api_hash=self.cfg.telegram.api_hash,
                bot_token=self.cfg.telegram.bot_token,
                in_memory=True,
            )

    async def start(
        self,
        message_handler: Callable[[Any], Awaitable[None]],
        callback_query_handler: Callable[[Any], Awaitable[None]] | None = None,
    ) -> None:
        """Start the Telegram client with message and callback query handlers."""
        if not self.client:
            logger.warning("telegram_client_not_available")
            return

        client_any: Any = self.client

        await client_any.start()

        # Register all handlers AFTER start() for reliable dispatch.
        # Using explicit add_handler() post-start ensures consistent behavior
        # across PyroTGFork versions.
        handler_count = 0

        if filters:
            from pyrogram.handlers import CallbackQueryHandler, MessageHandler as PyroMessageHandler

            async def _msg_handler(_client: Any, message: Any) -> None:
                await message_handler(message)

            message_filters = filters.private
            incoming_filter = getattr(filters, "incoming", None)
            if incoming_filter is not None:
                message_filters &= incoming_filter
            outgoing_filter = getattr(filters, "outgoing", None)
            if outgoing_filter is not None:
                message_filters &= ~outgoing_filter

            client_any.add_handler(PyroMessageHandler(_msg_handler, message_filters), group=0)
            handler_count += 1

            if callback_query_handler:

                async def _cb_handler(_client: Any, callback_query: Any) -> None:
                    await callback_query_handler(callback_query)

                client_any.add_handler(CallbackQueryHandler(_cb_handler), group=0)
                handler_count += 1

        logger.info(
            "handlers_registered",
            extra={
                "handler_count": handler_count,
                "has_callback": callback_query_handler is not None,
            },
        )
        await self._setup_bot_commands()
        await self._setup_forum_topics()
        await idle()

    async def _setup_bot_commands(self) -> None:
        """Set up bot commands for different languages."""
        if not self.client or not PYROGRAM_AVAILABLE or Client is object:
            return
        try:
            from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats

            # Main commands (ordered by most common usage)
            commands_en = [
                BotCommand("summarize", "Summarize a URL"),
                BotCommand("search", "Search your summaries"),
                BotCommand("unread", "Show unread articles"),
                BotCommand("read", "Mark article as read"),
                BotCommand("summarize_all", "Summarize multiple URLs"),
                BotCommand("cancel", "Cancel pending operation"),
                BotCommand("help", "Show help and usage"),
                BotCommand("start", "Welcome and instructions"),
                BotCommand("dbinfo", "Show database stats"),
                BotCommand("dbverify", "Verify database integrity"),
                BotCommand("clearcache", "Clear internal cache"),
                BotCommand("sync_karakeep", "Sync bookmarks from Karakeep"),
                BotCommand("digest", "Generate channel digest"),
                BotCommand("channels", "List subscribed channels"),
                BotCommand("subscribe", "Subscribe to a channel"),
                BotCommand("unsubscribe", "Unsubscribe from a channel"),
            ]
            commands_ru = [
                BotCommand("summarize", "Суммировать ссылку"),
                BotCommand("search", "Поиск по резюме"),
                BotCommand("unread", "Непрочитанные статьи"),
                BotCommand("read", "Отметить прочитанным"),
                BotCommand("summarize_all", "Суммировать несколько"),
                BotCommand("cancel", "Отменить операцию"),
                BotCommand("help", "Помощь и инструкция"),
                BotCommand("start", "Приветствие"),
                BotCommand("dbinfo", "Статистика БД"),
                BotCommand("dbverify", "Проверка БД"),
                BotCommand("clearcache", "Очистить кэш"),
                BotCommand("sync_karakeep", "Синхронизация Karakeep"),
                BotCommand("digest", "Дайджест каналов"),
                BotCommand("channels", "Список подписок"),
                BotCommand("subscribe", "Подписаться на канал"),
                BotCommand("unsubscribe", "Отписаться от канала"),
            ]
            try:
                client_any: Any = self.client
                # Default and private scope
                await client_any.set_bot_commands(commands_en)
                await client_any.set_bot_commands(
                    commands_en, scope=BotCommandScopeAllPrivateChats()
                )
                # Localized RU
                await client_any.set_bot_commands(commands_ru, language_code="ru")
                await client_any.set_bot_commands(
                    commands_ru,
                    scope=BotCommandScopeAllPrivateChats(),
                    language_code="ru",
                )

                # Set bot descriptions
                try:
                    await client_any.set_bot_description(
                        "Bite-Size Reader: Summarize URLs, YouTube videos, and forwarded posts. "
                        "Get structured summaries with key ideas, entities, and tags.",
                        language_code="en",
                    )
                    await client_any.set_bot_short_description(
                        "Summarize articles & videos into bite-sized insights",
                        language_code="en",
                    )
                    await client_any.set_bot_description(
                        "Bite-Size Reader: Резюме ссылок, YouTube видео и пересланных постов. "
                        "Структурированные саммари с ключевыми идеями, сущностями и тегами.",
                        language_code="ru",
                    )
                    await client_any.set_bot_short_description(
                        "Резюме статей и видео в краткие инсайты",
                        language_code="ru",
                    )
                except Exception:
                    pass

                # Set up persistent menu button that shows commands
                # The default behavior shows the command menu when button is tapped
                try:
                    import pyrogram.types as pyrogram_types

                    menu_button_cls = getattr(pyrogram_types, "BotMenuButtonCommands", None)
                    if menu_button_cls is None:
                        raise ImportError("BotMenuButtonCommands unavailable")
                    await client_any.set_chat_menu_button(menu_button=menu_button_cls())
                    logger.debug("menu_button_commands_set")
                except ImportError:
                    # Fallback: just set default menu button
                    with contextlib.suppress(Exception):
                        await client_any.set_chat_menu_button()
                except Exception as menu_error:
                    logger.debug(
                        "menu_button_set_fallback",
                        extra={"error": str(menu_error)},
                    )
                    # Fallback to default
                    with contextlib.suppress(Exception):
                        await client_any.set_chat_menu_button()

                logger.info(
                    "bot_commands_set",
                    extra={"count_en": len(commands_en), "count_ru": len(commands_ru)},
                )
            except Exception as e:
                logger.warning("bot_commands_set_failed", extra={"error": str(e)})
        except Exception:
            return

    async def _setup_forum_topics(self) -> None:
        """Initialize forum topics for allowed users' private chats.

        Creates default topic categories so summaries can be routed by topic.
        Only runs when topic_manager is set (forum topics enabled in config).
        """
        if self.topic_manager is None or not self.client:
            return
        if not self.cfg.telegram.allowed_user_ids:
            return

        for uid in self.cfg.telegram.allowed_user_ids:
            try:
                await self.topic_manager.ensure_default_topics(self.client, uid)
            except Exception as exc:
                logger.warning(
                    "forum_topics_setup_failed",
                    extra={"user_id": uid, "error": str(exc)},
                )


async def idle() -> None:
    """Simple idle loop to keep the client running."""
    try:
        # Wait forever (or until cancelled)
        await asyncio.Event().wait()
    except asyncio.CancelledError:  # pragma: no cover
        return
