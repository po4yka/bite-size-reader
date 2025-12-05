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
    _pyrogram_bootstrap_loop: asyncio.AbstractEventLoop | None = None
    _previous_loop: asyncio.AbstractEventLoop | None = None
    try:
        # Pyrogram's sync adapter tries to grab a running loop at import time.
        # Python 3.13+ raises when no loop exists, so we provision a temporary
        # one to keep the import compatible inside containers.
        try:
            _previous_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass

        if _previous_loop is None or _previous_loop.is_closed():
            _pyrogram_bootstrap_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_pyrogram_bootstrap_loop)

        # Runtime aliases that tests can monkeypatch
        from pyrogram import Client, filters
        from pyrogram.types import Message

        PYROGRAM_AVAILABLE = True
    except Exception:  # pragma: no cover - allow import in environments without deps
        Client = object
        filters = None
        Message = object
        PYROGRAM_AVAILABLE = False
    finally:
        if _pyrogram_bootstrap_loop is not None:
            try:
                if _previous_loop is not None and not _previous_loop.is_closed():
                    asyncio.set_event_loop(_previous_loop)
                else:
                    asyncio.set_event_loop(None)
            except Exception:
                pass

logger = logging.getLogger(__name__)


class TelegramClient:
    """Handles Pyrogram client setup and operations."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.client: Client | None = None

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

        # Register handlers only if filters are available
        if filters:
            # Register a simple on_message handler in private chats
            @client_any.on_message(filters.private)
            async def _handler(client: Any, message: Any) -> None:
                await message_handler(message)

            # Register callback query handler for inline button clicks
            if callback_query_handler:

                @client_any.on_callback_query()
                async def _callback_handler(client: Any, callback_query: Any) -> None:
                    await callback_query_handler(callback_query)

        await client_any.start()
        logger.info("bot_started")
        await self._setup_bot_commands()
        await idle()

    async def _setup_bot_commands(self) -> None:
        """Set up bot commands for different languages."""
        if not self.client or not PYROGRAM_AVAILABLE or Client is object:
            return
        try:
            from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats

            commands_en = [
                BotCommand("start", "Welcome and instructions"),
                BotCommand("help", "Show help and usage"),
                BotCommand("summarize", "Summarize a URL"),
                BotCommand("summarize_all", "Summarize multiple URLs from one message"),
                BotCommand("cancel", "Cancel pending URL or multi-link prompts"),
                BotCommand("unread", "Show list of unread articles"),
                BotCommand("read", "Mark article as read and view it"),
                BotCommand("dbverify", "Verify database integrity and reprocess"),
                BotCommand("dbinfo", "Show database overview"),
            ]
            commands_ru = [
                BotCommand("start", "Приветствие и инструкция"),
                BotCommand("help", "Показать помощь и инструкцию"),
                BotCommand("summarize", "Суммировать ссылку (или пришлите позже)"),
                BotCommand("summarize_all", "Суммировать несколько ссылок из сообщения"),
                BotCommand(
                    "cancel",
                    "Отменить ожидание ссылки или подтверждения нескольких ссылок",
                ),
                BotCommand("unread", "Показать список непрочитанных статей"),
                BotCommand(
                    "read", "Отметить статью как прочитанную и просмотреть (используйте /read <ID>)"
                ),
                BotCommand(
                    "dbverify",
                    "Проверить целостность базы данных и перезапустить обработку",
                ),
                BotCommand("dbinfo", "Показать состояние базы данных"),
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
                # Optional descriptions (if supported)
                try:
                    await client_any.set_bot_description(
                        "Summarize URLs and forwarded posts into structured JSON with reliable results.",
                        language_code="en",
                    )
                    await client_any.set_bot_short_description(
                        "Structured JSON summaries with smart fallbacks", language_code="en"
                    )
                    await client_any.set_bot_description(
                        "Улучшенные резюме ссылок и пересланных постов в формате JSON с повышенной надёжностью.",
                        language_code="ru",
                    )
                    await client_any.set_bot_short_description(
                        "Улучшенные JSON резюме с умными резервами", language_code="ru"
                    )
                except Exception:
                    pass
                # Ensure default menu button (best-effort)
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


async def idle() -> None:
    """Simple idle loop to keep the client running."""
    try:
        # Wait forever (or until cancelled)
        await asyncio.Event().wait()
    except asyncio.CancelledError:  # pragma: no cover
        return
