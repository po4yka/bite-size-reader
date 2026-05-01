"""Telethon runtime compatibility helpers for the existing bot surface."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

TELETHON_AVAILABLE = True
try:  # pragma: no cover - exercised when dependency is installed
    from telethon import Button, TelegramClient, events, functions, types
    from telethon.errors import SessionPasswordNeededError as _SessionPasswordNeededError
except Exception:  # pragma: no cover - allow import in minimal test envs
    Button = None
    TelegramClient = None
    events = None
    functions = None
    types = None

    class _SessionPasswordNeededError(Exception):  # type: ignore[no-redef]
        """Fallback exception used when Telethon is unavailable."""

    TELETHON_AVAILABLE = False

SessionPasswordNeededError = _SessionPasswordNeededError


class ParseMode(StrEnum):
    HTML = "html"
    MARKDOWN = "markdown"
    DISABLED = "disabled"


@dataclass(slots=True, frozen=True)
class WebAppInfo:
    url: str


@dataclass(slots=True, frozen=True)
class KeyboardButton:
    text: str
    request_contact: bool = False
    web_app: WebAppInfo | None = None


@dataclass(slots=True, frozen=True)
class ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]]
    resize_keyboard: bool = True
    one_time_keyboard: bool = True


@dataclass(slots=True, frozen=True)
class ReplyKeyboardRemove:
    remove_keyboard: bool = True


@dataclass(slots=True, frozen=True)
class InlineKeyboardButton:
    text: str
    callback_data: str | bytes | None = None
    url: str | None = None
    web_app: WebAppInfo | None = None
    style: str | None = None


@dataclass(slots=True, frozen=True)
class InlineKeyboardMarkup:
    inline_keyboard: list[list[InlineKeyboardButton]]


@dataclass(slots=True, frozen=True)
class BotCommand:
    command: str
    description: str


@dataclass(slots=True, frozen=True)
class BotCommandScopeAllPrivateChats:
    """Compatibility marker for the existing command setup code."""


def normalize_parse_mode(mode: str | ParseMode | None) -> str | None:
    if mode is None:
        return None
    raw = str(mode.value if isinstance(mode, ParseMode) else mode).lower()
    if raw in {"html", "parsemode.html"}:
        return "html"
    if raw in {"markdown", "md", "parsemode.markdown"}:
        return "markdown"
    if raw in {"disabled", "none", "parsemode.disabled"}:
        return None
    return str(mode)


def to_telethon_buttons(reply_markup: Any) -> Any:
    """Translate local keyboard dataclasses to Telethon button structures."""
    if reply_markup is None or Button is None:
        return None
    if isinstance(reply_markup, InlineKeyboardMarkup):
        rows = []
        for row in reply_markup.inline_keyboard:
            converted = [
                converted_button
                for button in row
                if (converted_button := _inline_button_to_telethon(button)) is not None
            ]
            rows.append(converted)
        return rows
    if isinstance(reply_markup, ReplyKeyboardMarkup):
        return [
            [_reply_button_to_telethon(button) for button in row] for row in reply_markup.keyboard
        ]
    if isinstance(reply_markup, ReplyKeyboardRemove):
        return Button.clear()
    return reply_markup


def _inline_button_to_telethon(button: InlineKeyboardButton) -> Any:
    if button.url:
        return Button.url(button.text, button.url)
    if button.web_app:
        # Telethon has no first-class WebApp button helper in all supported
        # versions. A URL button keeps the flow usable on older runtimes.
        return Button.url(button.text, button.web_app.url)
    data = button.callback_data or ""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return Button.inline(button.text, data=data)


def _reply_button_to_telethon(button: KeyboardButton) -> Any:
    if button.request_contact:
        return Button.request_phone(button.text)
    if button.web_app:
        return Button.url(button.text, button.web_app.url)
    return Button.text(button.text)


class TelethonBotClient:
    """Small compatibility wrapper around Telethon's bot client."""

    def __init__(
        self,
        *,
        name: str,
        api_id: int,
        api_hash: str,
        bot_token: str,
        session_dir: str | None = None,
    ) -> None:
        if TelegramClient is None:
            msg = "Telethon is not installed"
            raise RuntimeError(msg)
        session_name = name if session_dir is None else f"{session_dir.rstrip('/')}/{name}"
        self._bot_token = bot_token
        self._client = TelegramClient(session_name, api_id, api_hash)

    @property
    def raw(self) -> Any:
        return self._client

    @property
    def is_connected(self) -> bool:
        return bool(self._client.is_connected())

    async def start(self) -> None:
        await self._client.start(bot_token=self._bot_token)

    async def stop(self) -> None:
        await self._client.disconnect()

    async def __aenter__(self) -> TelethonBotClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.stop()

    def add_message_handler(self, handler: Any) -> None:
        if events is None:
            return

        @self._client.on(events.NewMessage(incoming=True))
        async def _on_message(event: Any) -> None:
            await handler(TelethonMessageAdapter(event, self))

    def add_callback_query_handler(self, handler: Any) -> None:
        if events is None:
            return

        @self._client.on(events.CallbackQuery)
        async def _on_callback(event: Any) -> None:
            await handler(TelethonCallbackQueryAdapter(event, self))

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
        parse_mode: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self._client.send_message(
            chat_id,
            text,
            buttons=to_telethon_buttons(reply_markup),
            parse_mode=normalize_parse_mode(parse_mode),
            **_filter_send_kwargs(kwargs),
        )

    async def delete_messages(self, chat_id: int, message_ids: list[int]) -> None:
        await self._client.delete_messages(chat_id, message_ids)

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_markup: Any | None = None,
        disable_web_page_preview: bool | None = None,
        **_kwargs: Any,
    ) -> Any:
        edit_kwargs: dict[str, Any] = {}
        if disable_web_page_preview is not None:
            edit_kwargs["link_preview"] = not bool(disable_web_page_preview)
        return await self._client.edit_message(
            chat_id,
            message_id,
            text,
            parse_mode=normalize_parse_mode(parse_mode),
            buttons=to_telethon_buttons(reply_markup),
            **edit_kwargs,
        )

    async def set_bot_commands(
        self,
        commands: list[BotCommand],
        *,
        scope: Any | None = None,
        language_code: str | None = None,
    ) -> None:
        if functions is None or types is None:
            return
        scope_obj = (
            types.BotCommandScopeUsers()
            if isinstance(scope, BotCommandScopeAllPrivateChats)
            else types.BotCommandScopeDefault()
        )
        await self._client(
            functions.bots.SetBotCommandsRequest(
                scope=scope_obj,
                lang_code=language_code or "",
                commands=[
                    types.BotCommand(command=cmd.command, description=cmd.description)
                    for cmd in commands
                ],
            )
        )

    async def set_bot_description(self, text: str, *, language_code: str | None = None) -> None:
        await self._set_bot_info(about=text, language_code=language_code)

    async def set_bot_short_description(
        self, text: str, *, language_code: str | None = None
    ) -> None:
        await self._set_bot_info(description=text, language_code=language_code)

    async def _set_bot_info(
        self,
        *,
        about: str | None = None,
        description: str | None = None,
        language_code: str | None = None,
    ) -> None:
        if functions is None:
            return
        with contextlib.suppress(Exception):
            await self._client(
                functions.bots.SetBotInfoRequest(
                    lang_code=language_code or "",
                    about=about,
                    description=description,
                )
            )

    async def set_chat_menu_button(self, **_kwargs: Any) -> None:
        return None

    async def send_custom_request(self, custom_method: str, params: dict[str, Any]) -> Any:
        if functions is None or types is None:
            msg = "telethon_raw_functions_unavailable"
            raise RuntimeError(msg)
        import json

        return await self._client(
            functions.bots.SendCustomRequestRequest(
                custom_method=custom_method,
                params=types.DataJSON(data=json.dumps(params, ensure_ascii=False)),
            )
        )


class TelethonUserClient:
    """Small wrapper around a Telethon user session."""

    def __init__(self, *, session_path: str, api_id: int, api_hash: str) -> None:
        if TelegramClient is None:
            msg = "Telethon is not installed"
            raise RuntimeError(msg)
        self._client = TelegramClient(session_path, api_id, api_hash)

    @property
    def raw(self) -> Any:
        return self._client

    @property
    def is_connected(self) -> bool:
        return bool(self._client.is_connected())

    async def connect(self) -> None:
        await self._client.connect()

    async def start(self, *, interactive: bool = False) -> None:
        if interactive:
            await self._client.start()
            return
        await self._client.connect()
        if not await self._client.is_user_authorized():
            msg = "Telethon user session is not authorized; run /init_session first"
            raise RuntimeError(msg)

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def send_code(self, phone: str) -> Any:
        return await self._client.send_code_request(phone)

    async def sign_in(
        self,
        *,
        phone_number: str | None = None,
        phone_code_hash: str | None = None,
        phone_code: str | None = None,
        password: str | None = None,
    ) -> Any:
        if password is not None:
            return await self._client.sign_in(password=password)
        return await self._client.sign_in(
            phone=phone_number,
            code=phone_code,
            phone_code_hash=phone_code_hash,
        )

    async def check_password(self, password: str) -> Any:
        return await self.sign_in(password=password)

    async def get_me(self) -> Any:
        return await self._client.get_me()

    def get_chat_history(self, channel_username: str) -> Any:
        return self._client.iter_messages(channel_username)

    async def get_chat(self, username: str) -> Any:
        return await self._client.get_entity(username)


class TelethonMessageAdapter:
    """Expose a Telethon message event with the methods used by handlers."""

    def __init__(self, event: Any, bot: TelethonBotClient) -> None:
        self._event = event
        self._bot = bot
        self._message = event.message
        self._client = bot

    def __getattr__(self, name: str) -> Any:
        return getattr(self._message, name)

    @property
    def id(self) -> int:
        return int(getattr(self._message, "id", 0))

    @property
    def chat(self) -> Any:
        chat_id = getattr(self._message, "chat_id", None)
        return getattr(self._message, "chat", None) or _Object(id=chat_id)

    @property
    def from_user(self) -> Any:
        sender = getattr(self._message, "sender", None) or getattr(self._event, "sender", None)
        if sender is None:
            return None
        return _Object(
            id=getattr(sender, "id", None),
            first_name=getattr(sender, "first_name", None),
            username=getattr(sender, "username", None),
            is_bot=getattr(sender, "bot", False),
        )

    @property
    def text(self) -> str | None:
        return getattr(self._message, "raw_text", None) or getattr(self._message, "text", None)

    @property
    def caption(self) -> str | None:
        return None

    async def reply_text(self, text: str, **kwargs: Any) -> Any:
        return await self._event.reply(
            text,
            buttons=to_telethon_buttons(kwargs.pop("reply_markup", None)),
            parse_mode=normalize_parse_mode(kwargs.pop("parse_mode", None)),
            **_filter_send_kwargs(kwargs),
        )

    async def reply_document(
        self, document: Any, *, caption: str | None = None, **kwargs: Any
    ) -> Any:
        return await self._client.raw.send_file(
            self.chat.id,
            document,
            caption=caption,
            buttons=to_telethon_buttons(kwargs.pop("reply_markup", None)),
        )


class TelethonCallbackQueryAdapter:
    """Expose callback query fields used by the callback handler."""

    def __init__(self, event: Any, bot: TelethonBotClient) -> None:
        self._event = event
        self._bot = bot
        data = getattr(event, "data", b"")
        self.data = data.decode("utf-8") if isinstance(data, bytes) else str(data)
        self.message = (
            TelethonMessageAdapter(event, bot) if getattr(event, "message", None) else None
        )
        self.from_user = _Object(id=getattr(event, "sender_id", None))

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        await self._event.answer(text or "", alert=show_alert)


@dataclass(slots=True)
class _Object:
    id: Any = None
    first_name: str | None = None
    username: str | None = None
    is_bot: bool = False


def _filter_send_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    allowed = {"link_preview", "file", "silent"}
    return {key: value for key, value in kwargs.items() if key in allowed}
