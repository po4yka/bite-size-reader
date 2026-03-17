"""Direct tests for Mini App-related Telegram command handlers."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.telegram.command_handlers.init_session_handler import InitSessionHandlerImpl
from app.adapters.telegram.command_handlers.settings_handler import SettingsHandlerImpl
from app.adapters.telegram.session_init_state import SESSION_INIT_TTL_SECONDS, SessionInitState


def _make_settings_ctx() -> tuple[Any, AsyncMock]:
    safe_reply = AsyncMock()
    ctx = SimpleNamespace(
        message=MagicMock(),
        text="/settings",
        uid=123456789,
        chat_id=123456789,
        correlation_id="cid-settings-1",
        interaction_id=0,
        start_time=time.time(),
        user_repo=MagicMock(),
        response_formatter=SimpleNamespace(safe_reply=safe_reply),
        audit_func=MagicMock(),
    )
    return ctx, safe_reply


def _make_init_handler() -> InitSessionHandlerImpl:
    cfg = SimpleNamespace(
        digest=SimpleNamespace(enabled=True, session_name="test-userbot"),
        telegram=SimpleNamespace(api_id=1, api_hash="hash", api_base_url="https://api.example.com"),
    )
    return InitSessionHandlerImpl(
        cfg=cast("Any", cfg),
        response_formatter=cast("Any", SimpleNamespace(safe_reply=AsyncMock())),
    )


def _make_contact_message(
    *,
    uid: int,
    phone_number: str = "+1234567890",
    contact_user_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=uid),
        contact=SimpleNamespace(phone_number=phone_number, user_id=contact_user_id),
        chat=SimpleNamespace(id=uid),
        _client=SimpleNamespace(delete_messages=AsyncMock()),
        reply_text=AsyncMock(return_value=SimpleNamespace(id=777)),
    )


class TestSettingsHandlerImpl:
    @pytest.mark.asyncio
    async def test_handle_settings_requires_api_base_url(self) -> None:
        ctx, safe_reply = _make_settings_ctx()
        handler = SettingsHandlerImpl(
            verbosity_resolver=None,
            cfg=cast("Any", SimpleNamespace(telegram=SimpleNamespace(api_base_url=""))),
        )

        await handler.handle_settings(cast("Any", ctx))

        safe_reply.assert_awaited_once()
        assert safe_reply.await_args.args[0] is ctx.message
        assert "API base URL not configured" in safe_reply.await_args.args[1]

    @pytest.mark.asyncio
    async def test_handle_settings_sends_digest_webapp_button(self) -> None:
        pytest.importorskip("pyrogram")

        ctx, safe_reply = _make_settings_ctx()
        handler = SettingsHandlerImpl(
            verbosity_resolver=None,
            cfg=cast(
                "Any",
                SimpleNamespace(telegram=SimpleNamespace(api_base_url="https://example.com/")),
            ),
        )

        await handler.handle_settings(cast("Any", ctx))

        safe_reply.assert_awaited_once()
        assert safe_reply.await_args.args[0] is ctx.message
        reply_markup = safe_reply.await_args.kwargs["reply_markup"]
        button = reply_markup.inline_keyboard[0][0]
        assert button.text == "Digest Settings"
        assert button.web_app.url == "https://example.com/web/digest"


class TestInitSessionHandlerImpl:
    @pytest.mark.asyncio
    async def test_handle_contact_rejects_mismatched_contact_owner(self) -> None:
        handler = _make_init_handler()
        uid = 101
        handler._sessions[uid] = SessionInitState(step="waiting_contact")
        message = _make_contact_message(uid=uid, contact_user_id=202)

        await handler.handle_contact(message)

        message.reply_text.assert_awaited_once()
        assert "share your own phone number" in message.reply_text.await_args.args[0]
        assert handler._sessions[uid].phone_number == ""
        assert handler._sessions[uid].step == "waiting_contact"

    @pytest.mark.asyncio
    async def test_handle_contact_send_code_failure_does_not_leak_exception_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("pyrogram")

        handler = _make_init_handler()
        uid = 303
        handler._sessions[uid] = SessionInitState(step="waiting_contact")
        message = _make_contact_message(uid=uid, contact_user_id=uid)

        class _FailingClient:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs

            async def connect(self) -> None:
                return None

            async def send_code(self, _phone: str) -> None:
                raise RuntimeError("internal-secret-send-code-error")

            async def disconnect(self) -> None:
                return None

        monkeypatch.setattr("pyrogram.Client", _FailingClient)
        cleanup = AsyncMock()
        cast("Any", handler)._cleanup = cleanup

        await handler.handle_contact(message)

        sent_texts = [call.args[0] for call in message.reply_text.await_args_list if call.args]
        assert any("Failed to send verification code." in text for text in sent_texts)
        assert all("internal-secret-send-code-error" not in text for text in sent_texts)
        assert handler._sessions[uid].step == "waiting_contact"
        cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_has_active_session_disconnects_expired_client(self) -> None:
        handler = _make_init_handler()
        uid = 505
        client = SimpleNamespace(disconnect=AsyncMock())
        state = SessionInitState(client=client, step="waiting_otp")
        state.created_at = time.time() - SESSION_INIT_TTL_SECONDS - 1
        handler._sessions[uid] = state

        assert handler.has_active_session(uid) is False
        await asyncio.sleep(0)

        client.disconnect.assert_awaited_once()
        assert uid not in handler._sessions

    @pytest.mark.asyncio
    async def test_handle_otp_failure_does_not_leak_exception_text(self) -> None:
        pytest.importorskip("pyrogram.errors")

        handler = _make_init_handler()
        uid = 404
        state = SessionInitState(
            phone_number="+1234567890",
            phone_code_hash="phone-hash",
            client=SimpleNamespace(
                sign_in=AsyncMock(side_effect=RuntimeError("otp-secret-error")),
                get_me=AsyncMock(),
                disconnect=AsyncMock(),
            ),
            step="waiting_otp",
        )
        handler._sessions[uid] = state
        cleanup = AsyncMock()
        cast("Any", handler)._cleanup = cleanup
        message = _make_contact_message(uid=uid, contact_user_id=uid)

        await handler._handle_otp(message, state, uid, "12345")

        sent_texts = [call.args[0] for call in message.reply_text.await_args_list if call.args]
        assert any("Sign-in failed." in text for text in sent_texts)
        assert all("otp-secret-error" not in text for text in sent_texts)
        assert handler._sessions[uid] is state
        cleanup.assert_awaited_once()
