from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.adapters.telegram.command_handlers.init_session_handler import InitSessionHandler
from app.adapters.telegram.session_init_state import SessionInitState
from app.adapters.telegram.telethon_compat import InlineKeyboardMarkup, ReplyKeyboardMarkup


def test_settings_and_init_keyboards_are_local_telethon_compat_types() -> None:
    from app.adapters.telegram.command_handlers.settings_handler import SettingsHandler

    handler = SettingsHandler(
        verbosity_resolver=None,
        cfg=cast("Any", SimpleNamespace(telegram=SimpleNamespace(api_base_url="https://x.test"))),
    )
    assert handler is not None
    assert ReplyKeyboardMarkup.__name__ == "ReplyKeyboardMarkup"
    assert InlineKeyboardMarkup.__name__ == "InlineKeyboardMarkup"


@pytest.mark.asyncio
async def test_init_session_promotes_pending_session_after_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = SimpleNamespace(
        digest=SimpleNamespace(enabled=True, session_name="digest_userbot"),
        telegram=SimpleNamespace(api_id=1, api_hash="hash", api_base_url="https://api.example.com"),
    )
    handler = InitSessionHandler(cast("Any", cfg), response_formatter=cast("Any", object()))
    state = SessionInitState(pending_session_name="digest_userbot.telethon_pending")
    session_dir = tmp_path
    pending = session_dir / "digest_userbot.telethon_pending.session"
    final = session_dir / "digest_userbot.session"
    pending.write_text("new", encoding="utf-8")
    final.write_text("old", encoding="utf-8")

    import app.adapters.telegram.command_handlers.init_session_handler as module

    original_path = module.Path

    def _path_patch(value: str) -> Path:
        if value == "/data":
            return session_dir
        return original_path(value)

    monkeypatch.setattr(module, "Path", _path_patch)
    await handler._promote_pending_session(state)

    assert final.read_text(encoding="utf-8") == "new"
    assert (session_dir / "digest_userbot.legacy.bak.session").read_text(encoding="utf-8") == "old"


def test_active_app_code_has_no_pyrogram_imports() -> None:
    root = Path("app")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "from pyrogram" in text or "import pyrogram" in text:
            offenders.append(str(path))
    assert offenders == []


@pytest.mark.asyncio
async def test_telethon_bot_client_edit_message_text_invokes_telethon_edit_message() -> None:
    """Regression: progress-message edits must reach Telethon's edit_message API.

    The response sender's edit flow checks ``hasattr(client, "edit_message_text")``;
    when that attribute was missing the edit silently failed and every progress
    tick posted a fresh message instead of editing in place.
    """
    from app.adapters.telegram.telethon_compat import TelethonBotClient

    captured: dict[str, Any] = {}

    class _FakeTelethon:
        async def edit_message(
            self,
            entity: int,
            message_id: int,
            text: str,
            *,
            parse_mode: Any | None = None,
            buttons: Any | None = None,
            link_preview: bool | None = None,
        ) -> str:
            captured.update(
                entity=entity,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                buttons=buttons,
                link_preview=link_preview,
            )
            return "edited"

    client = TelethonBotClient.__new__(TelethonBotClient)
    client._client = _FakeTelethon()

    assert hasattr(client, "edit_message_text")
    result = await client.edit_message_text(
        chat_id=42,
        message_id=7,
        text="<b>hello</b>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    assert result == "edited"
    assert captured["entity"] == 42
    assert captured["message_id"] == 7
    assert captured["text"] == "<b>hello</b>"
    assert captured["parse_mode"] == "html"
    assert captured["link_preview"] is False
