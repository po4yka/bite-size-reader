"""TTS /listen command handler.

Generates audio from a summary and sends it as a Telegram voice/audio message.
User replies to a summary message with /listen to trigger generation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.adapters.telegram.command_handlers.base_handler import HandlerDependenciesMixin
from app.db.models import Request, Summary
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )

logger = logging.getLogger(__name__)


class ListenHandlerImpl(HandlerDependenciesMixin):
    """Handle /listen command -- generate and send audio summary."""

    async def handle_listen(self, ctx: CommandExecutionContext) -> None:
        """Handle /listen command.

        The user should reply to a bot summary message with /listen.
        We look up the summary from the replied-to message and generate audio.
        """
        logger.info(
            "command_listen",
            extra={"uid": ctx.uid, "cid": ctx.correlation_id},
        )

        if not self._cfg.tts.enabled:
            await self._formatter.safe_reply(
                ctx.message,
                "TTS is not enabled. Set ELEVENLABS_ENABLED=true and ELEVENLABS_API_KEY.",
            )
            return

        if not self._cfg.tts.api_key:
            await self._formatter.safe_reply(
                ctx.message,
                "ElevenLabs API key not configured. Set ELEVENLABS_API_KEY.",
            )
            return

        # Find the summary from the replied-to message
        reply = getattr(ctx.message, "reply_to_message", None)
        if reply is None:
            await self._formatter.safe_reply(
                ctx.message,
                "Reply to a summary message with /listen to generate audio.",
            )
            return

        reply_msg_id = getattr(reply, "id", None) or getattr(reply, "message_id", None)
        if reply_msg_id is None:
            await self._formatter.safe_reply(
                ctx.message,
                "Could not identify the replied message.",
            )
            return

        # Look up summary by the replied message's input_message_id
        summary = self._find_summary_for_message(reply_msg_id, ctx.uid)
        if summary is None:
            await self._formatter.safe_reply(
                ctx.message,
                "No summary found for that message. Reply to a summary message.",
            )
            return

        # Generate audio
        await self._formatter.safe_reply(ctx.message, "Generating audio...")

        from app.services.tts_service import TTSService

        service = TTSService(self._cfg.tts)
        try:
            result = await service.generate_audio(summary.id)
        finally:
            await service.close()

        if result.status == "error":
            await self._formatter.safe_reply(
                ctx.message,
                f"Audio generation failed: {result.error}",
            )
            return

        if not result.file_path:
            await self._formatter.safe_reply(
                ctx.message, "Audio generation completed but file not found."
            )
            return

        # Send audio file
        await self._send_audio(ctx, result.file_path, summary)

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type="listen_audio",
                start_time=ctx.start_time,
                logger_=logger,
            )

    @staticmethod
    def _find_summary_for_message(message_id: int, user_id: int) -> Summary | None:
        """Find a summary associated with a Telegram message ID for a given user.

        Queries by bot_reply_message_id first (the ID of the bot's outbound summary
        message), then falls back to input_message_id for rows created before this
        field was introduced.
        """
        try:
            result = (
                Summary.select()
                .join(Request)
                .where((Request.bot_reply_message_id == message_id) & (Request.user_id == user_id))
                .first()
            )
            if result:
                return result
            # Fallback for rows created before bot_reply_message_id was added
            return (
                Summary.select()
                .join(Request)
                .where((Request.input_message_id == message_id) & (Request.user_id == user_id))
                .first()
            )
        except Exception:
            return None

    async def _send_audio(
        self,
        ctx: CommandExecutionContext,
        file_path: str,
        summary: Summary,
    ) -> None:
        """Send audio file via Telegram."""
        try:
            client = getattr(getattr(self._formatter, "_telegram_client", None), "client", None)
            # Try response_sender's telegram_client first
            if client is None:
                sender = getattr(self._formatter, "response_sender", None)
                if sender is not None:
                    client = getattr(getattr(sender, "_telegram_client", None), "client", None)

            if client is not None and hasattr(client, "send_audio"):
                payload = summary.json_payload or {}
                title = str(payload.get("title", "Summary"))[:64]
                chat_id = getattr(getattr(ctx.message, "chat", None), "id", None)
                if chat_id:
                    await client.send_audio(
                        chat_id=chat_id,
                        audio=file_path,
                        caption=f"Audio: {title}",
                    )
                    return

            # Fallback: just confirm generation
            await self._formatter.safe_reply(
                ctx.message,
                "Audio generated successfully. Download is available via the web app.",
            )
        except Exception as exc:
            logger.error(
                "listen_send_audio_failed",
                extra={"error": str(exc), "cid": ctx.correlation_id},
            )
            await self._formatter.safe_reply(
                ctx.message,
                "Audio generated but failed to send. Try the web app.",
            )
