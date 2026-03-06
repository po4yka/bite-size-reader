"""Bot-mediated userbot session initialization via /init_session command.

Replaces the interactive CLI tool with an in-bot flow:
  1. /init_session -> bot sends contact-sharing keyboard
  2. User shares phone number -> bot calls send_code()
  3. Bot sends Mini App button -> user enters OTP
  4. Bot calls sign_in() -> success or 2FA prompt
  5. (optional) User enters 2FA password -> bot calls check_password()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.command_handlers.decorators import audit_command, track_interaction
from app.adapters.telegram.session_init_state import SESSION_INIT_TTL_SECONDS, SessionInitState
from app.core.async_utils import raise_if_cancelled

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.config import AppConfig

logger = logging.getLogger(__name__)

# Mini App URL template - served by FastAPI at /static/
_MINI_APP_PATH = "/static/init_session.html"


class InitSessionHandlerImpl:
    """Handles the multi-step userbot session initialization flow."""

    def __init__(
        self,
        cfg: AppConfig,
        response_formatter: ResponseFormatter,
    ) -> None:
        self._cfg = cfg
        self._formatter = response_formatter
        self._sessions: dict[int, SessionInitState] = {}

    def has_active_session(self, uid: int) -> bool:
        """Check if a user has an active session init flow."""
        state = self._sessions.get(uid)
        if state is None:
            return False
        if state.is_expired:
            self._sessions.pop(uid, None)
            return False
        return True

    # ------------------------------------------------------------------
    # Step 1: /init_session command
    # ------------------------------------------------------------------

    @audit_command("command_init_session")
    @track_interaction("init_session")
    async def handle_init_session(self, ctx: CommandExecutionContext) -> None:
        """Entry point: send contact-sharing keyboard."""
        if not self._cfg.digest.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "Channel digest is not enabled.\n\nSet `DIGEST_ENABLED=true` in your environment.",
            )
            return

        # Clean up any expired sessions
        self._cleanup_expired()

        # Warn if already in progress
        if ctx.uid in self._sessions:
            await self._cleanup(ctx.uid, ctx.message)

        # Check if session file already exists
        session_dir = Path("/data")
        session_path = session_dir / f"{self._cfg.digest.session_name}.session"
        warning = ""
        if session_path.exists():
            warning = "A session file already exists. This will overwrite it.\n\n"

        # Create new state
        self._sessions[ctx.uid] = SessionInitState(step="waiting_contact")

        # Send contact keyboard
        from pyrogram.types import KeyboardButton, ReplyKeyboardMarkup

        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("Share phone number", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        sent = await ctx.message.reply_text(
            f"{warning}To initialize the userbot session, share your phone number.",
            reply_markup=keyboard,
        )
        if sent and hasattr(sent, "id"):
            self._sessions[ctx.uid].message_ids.append(sent.id)

    # ------------------------------------------------------------------
    # Step 2: Contact received -> send_code()
    # ------------------------------------------------------------------

    async def handle_contact(self, message: Any) -> None:
        """Handle shared contact: extract phone, call send_code(), send Mini App button."""
        uid = message.from_user.id if message.from_user else None
        if uid is None or uid not in self._sessions:
            return

        state = self._sessions[uid]
        if state.step != "waiting_contact":
            return

        # Track this message for cleanup
        if hasattr(message, "id"):
            state.message_ids.append(message.id)

        contact = message.contact
        if not contact or not contact.phone_number:
            await self._reply_and_track(message, state, "No phone number received. Try again.")
            return

        phone = contact.phone_number
        if not phone.startswith("+"):
            phone = f"+{phone}"

        state.phone_number = phone

        # Send status
        await self._reply_and_track(
            message, state, "Phone number received. Sending verification code..."
        )

        try:
            from pyrogram import Client

            session_dir = Path("/data")
            session_dir.mkdir(parents=True, exist_ok=True)
            session_path = session_dir / self._cfg.digest.session_name

            client = Client(
                name=str(session_path),
                api_id=self._cfg.telegram.api_id,
                api_hash=self._cfg.telegram.api_hash,
            )

            await client.connect()
            sent_code = await client.send_code(phone)

            state.client = client
            state.phone_code_hash = sent_code.phone_code_hash
            state.step = "waiting_otp"

            # Send Mini App button for OTP entry
            await self._send_webapp_button(message, state, mode="otp")

        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "init_session_send_code_failed",
                extra={"uid": uid, "error": str(exc)},
            )
            await self._reply_and_track(message, state, f"Failed to send verification code: {exc}")
            await self._cleanup(uid, message)

    # ------------------------------------------------------------------
    # Step 3/4: Web App data (OTP or 2FA)
    # ------------------------------------------------------------------

    async def handle_web_app_data(self, message: Any) -> None:
        """Handle Mini App sendData() with OTP or 2FA password."""
        uid = message.from_user.id if message.from_user else None
        if uid is None or uid not in self._sessions:
            return

        state = self._sessions[uid]

        if hasattr(message, "id"):
            state.message_ids.append(message.id)

        try:
            data = json.loads(message.web_app_data.data)
        except (json.JSONDecodeError, AttributeError):
            await self._reply_and_track(message, state, "Invalid data received from Mini App.")
            return

        mode = data.get("mode")
        value = data.get("value", "").strip()

        if not value:
            await self._reply_and_track(message, state, "Empty value received. Please try again.")
            return

        if mode == "otp" and state.step == "waiting_otp":
            await self._handle_otp(message, state, uid, value)
        elif mode == "2fa" and state.step == "waiting_2fa":
            await self._handle_2fa(message, state, uid, value)
        else:
            await self._reply_and_track(
                message, state, f"Unexpected input (mode={mode}, step={state.step})."
            )

    async def _handle_otp(self, message: Any, state: SessionInitState, uid: int, code: str) -> None:
        """Process OTP code via sign_in()."""
        from pyrogram.errors import SessionPasswordNeeded

        try:
            await state.client.sign_in(
                phone_number=state.phone_number,
                phone_code_hash=state.phone_code_hash,
                phone_code=code,
            )
            # Success
            me = await state.client.get_me()
            await state.client.disconnect()
            state.client = None

            await self._reply_and_track(
                message,
                state,
                f"Session created for {me.first_name} (ID: {me.id}).\n\n"
                "You can now use `/digest` to generate channel digests.",
            )
            logger.info(
                "init_session_complete",
                extra={"uid": uid, "userbot_id": me.id},
            )
            await self._cleanup(uid, message, delete_messages=True)

        except SessionPasswordNeeded:
            state.step = "waiting_2fa"
            await self._send_webapp_button(message, state, mode="2fa")

        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "init_session_sign_in_failed",
                extra={"uid": uid, "error": str(exc)},
            )
            await self._reply_and_track(message, state, f"Sign-in failed: {exc}")
            await self._cleanup(uid, message)

    async def _handle_2fa(
        self, message: Any, state: SessionInitState, uid: int, password: str
    ) -> None:
        """Process 2FA password via check_password()."""
        try:
            await state.client.check_password(password)
            me = await state.client.get_me()
            await state.client.disconnect()
            state.client = None

            await self._reply_and_track(
                message,
                state,
                f"Session created for {me.first_name} (ID: {me.id}).\n\n"
                "You can now use `/digest` to generate channel digests.",
            )
            logger.info(
                "init_session_2fa_complete",
                extra={"uid": uid, "userbot_id": me.id},
            )
            await self._cleanup(uid, message, delete_messages=True)

        except Exception as exc:
            raise_if_cancelled(exc)
            logger.exception(
                "init_session_2fa_failed",
                extra={"uid": uid, "error": str(exc)},
            )
            await self._reply_and_track(message, state, f"2FA authentication failed: {exc}")
            await self._cleanup(uid, message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_webapp_button(
        self, message: Any, state: SessionInitState, *, mode: str
    ) -> None:
        """Send a ReplyKeyboardMarkup with a web_app button."""
        from pyrogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

        api_base = self._cfg.telegram.api_base_url
        if not api_base:
            await self._reply_and_track(
                message,
                state,
                "API base URL not configured. Set `API_BASE_URL` in your environment.",
            )
            return

        url = f"{api_base.rstrip('/')}{_MINI_APP_PATH}?mode={mode}"
        label = "Enter verification code" if mode == "otp" else "Enter 2FA password"

        keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton(label, web_app=WebAppInfo(url=url))]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        sent = await message.reply_text(
            f"Tap the button below to enter your {'verification code' if mode == 'otp' else '2FA password'}.",
            reply_markup=keyboard,
        )
        if sent and hasattr(sent, "id"):
            state.message_ids.append(sent.id)

    async def _reply_and_track(self, message: Any, state: SessionInitState, text: str) -> Any:
        """Reply to message and track the reply message ID for cleanup."""
        try:
            sent = await message.reply_text(text)
            if sent and hasattr(sent, "id"):
                state.message_ids.append(sent.id)
            return sent
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning("init_session_reply_failed", extra={"error": str(exc)})
            return None

    async def _cleanup(self, uid: int, message: Any, *, delete_messages: bool = False) -> None:
        """Disconnect client and remove state. Optionally delete tracked messages."""
        state = self._sessions.pop(uid, None)
        if state is None:
            return

        # Disconnect pyrogram client if still connected
        if state.client is not None:
            try:
                await state.client.disconnect()
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.debug("init_session_disconnect_error", extra={"error": str(exc)})

        # Remove reply keyboard
        try:
            from pyrogram.types import ReplyKeyboardRemove

            await message.reply_text(".", reply_markup=ReplyKeyboardRemove())
            # Delete the "." message immediately
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.debug("init_session_keyboard_remove_failed", extra={"error": str(exc)})

        # Delete tracked messages
        if delete_messages and state.message_ids:
            try:
                chat_id = message.chat.id if message.chat else None
                if chat_id is not None:
                    # Pyrogram bot can delete messages in private chats
                    client = message._client
                    await client.delete_messages(chat_id, state.message_ids)
            except Exception as exc:
                raise_if_cancelled(exc)
                logger.debug(
                    "init_session_message_cleanup_failed",
                    extra={"error": str(exc), "count": len(state.message_ids)},
                )

    def _cleanup_expired(self) -> None:
        """Remove any sessions that have exceeded the TTL."""
        expired = [uid for uid, s in self._sessions.items() if s.is_expired]
        for uid in expired:
            state = self._sessions.pop(uid)
            if state.client is not None:
                # Fire-and-forget disconnect for expired sessions
                try:
                    import asyncio

                    asyncio.get_event_loop().create_task(state.client.disconnect())
                except Exception as exc:
                    logger.debug(
                        "init_session_disconnect_schedule_failed",
                        extra={"uid": uid, "error": str(exc)},
                    )
            logger.info(
                "init_session_expired",
                extra={"uid": uid, "ttl": SESSION_INIT_TTL_SECONDS},
            )
