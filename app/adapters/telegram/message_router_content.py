"""Content routing for Telegram messages."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
from typing import Any

from app.adapters.telegram.message_router_helpers import (
    handle_document_file,
    is_txt_file_with_urls,
)
from app.core.ui_strings import t
from app.core.url_utils import looks_like_url
from app.db.user_interactions import async_safe_update_user_interaction

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageRouterContentMixin:
    """Command/content dispatch for MessageRouter."""

    async def _route_message_content(
        self,
        message: Any,
        text: str,
        uid: int,
        has_forward: bool,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Route message to appropriate handler based on content."""
        if getattr(message, "contact", None) and self.command_processor.has_active_init_session(
            uid
        ):
            await self.command_processor.handle_init_session_contact(message)
            return

        if getattr(
            message, "web_app_data", None
        ) and self.command_processor.has_active_init_session(uid):
            await self.command_processor.handle_init_session_webapp(message)
            return

        if await self._route_command_message(
            message,
            text,
            uid,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return

        if has_forward and await self._route_forward_message(
            message,
            correlation_id,
            interaction_id,
            start_time,
        ):
            return

        if await self.url_handler.is_awaiting_url(uid) and looks_like_url(text):
            await self.url_handler.handle_awaited_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if text and looks_like_url(text):
            await self.url_handler.handle_direct_url(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return

        if is_txt_file_with_urls(message):
            await handle_document_file(self, message, correlation_id, interaction_id, start_time)
            return

        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return

        await self.response_formatter.safe_reply(message, t("fallback_prompt", self._lang))
        logger.debug(
            "unknown_input",
            extra={
                "has_forward": bool(getattr(message, "forward_from_chat", None)),
                "text_len": len(text),
            },
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="unknown_input",
                start_time=start_time,
                logger_=logger,
            )

    async def _route_command_message(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        """Route command message. Returns True when command was handled."""
        if text.startswith("/start"):
            await self.command_processor.handle_start_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/help"):
            await self.command_processor.handle_help_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/dbinfo"):
            await self.command_processor.handle_dbinfo_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/dbverify"):
            await self.command_processor.handle_dbverify_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/clearcache"):
            await self.command_processor.handle_clearcache_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        for local_command in ("/finddb", "/findlocal"):
            if text.startswith(local_command):
                await self.command_processor.handle_find_local_command(
                    message,
                    text,
                    uid,
                    correlation_id,
                    interaction_id,
                    start_time,
                    command=local_command,
                )
                return True

        for online_command in ("/findweb", "/findonline", "/find"):
            if text.startswith(online_command):
                await self.command_processor.handle_find_online_command(
                    message,
                    text,
                    uid,
                    correlation_id,
                    interaction_id,
                    start_time,
                    command=online_command,
                )
                return True

        if text.startswith("/summarize_all"):
            await self.command_processor.handle_summarize_all_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/summarize"):
            action, _should_continue = await self.command_processor.handle_summarize_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            if action == "awaiting_url":
                await self.url_handler.add_awaiting_user(uid)
            return True

        if text.startswith("/cancel"):
            await self.command_processor.handle_cancel_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/unread"):
            await self.command_processor.handle_unread_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/read"):
            await self.command_processor.handle_read_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/search"):
            await self.command_processor.handle_search_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/sync_karakeep"):
            await self.command_processor.handle_sync_karakeep_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/cdigest"):
            await self.command_processor.handle_cdigest_command(
                message,
                text,
                uid,
                correlation_id,
                interaction_id,
                start_time,
            )
            return True

        if text.startswith("/digest"):
            await self.command_processor.handle_digest_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/channels"):
            await self.command_processor.handle_channels_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/subscribe"):
            await self.command_processor.handle_subscribe_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/unsubscribe"):
            await self.command_processor.handle_unsubscribe_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/init_session"):
            await self.command_processor.handle_init_session_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/settings"):
            await self.command_processor.handle_settings_command(
                message, text, uid, correlation_id, interaction_id, start_time
            )
            return True

        if text.startswith("/debug"):
            await self.command_processor.handle_debug_command(
                message, uid, correlation_id, interaction_id, start_time
            )
            return True

        return False

    async def _route_forward_message(
        self,
        message: Any,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        """Route forwarded message. Returns True when handled."""
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_msg_id = getattr(message, "forward_from_message_id", None)
        fwd_from_user = getattr(message, "forward_from", None)
        fwd_sender_name = getattr(message, "forward_sender_name", None)

        if fwd_chat is not None and fwd_msg_id is not None:
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        if fwd_from_user is not None or fwd_sender_name:
            fwd_text = (
                getattr(message, "text", None) or getattr(message, "caption", None) or ""
            ).strip()
            if fwd_text:
                await self.forward_processor.handle_forward_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return True
            if self.attachment_processor and self._should_handle_attachment(message):
                await self.attachment_processor.handle_attachment_flow(
                    message, correlation_id=correlation_id, interaction_id=interaction_id
                )
                return True
            logger.info(
                "forward_skipped_no_text",
                extra={
                    "cid": correlation_id,
                    "has_fwd_user": fwd_from_user is not None,
                    "has_fwd_sender_name": bool(fwd_sender_name),
                },
            )
            await self.response_formatter.safe_reply(
                message,
                "This forwarded message has no text content to summarize. "
                "Please forward a message that contains text.",
            )
            if interaction_id:
                await async_safe_update_user_interaction(
                    self.user_repo,
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="forward_no_text",
                    start_time=start_time,
                    logger_=logger,
                )
            return True

        fwd_text = (
            getattr(message, "text", None) or getattr(message, "caption", None) or ""
        ).strip()
        if fwd_text:
            await self.forward_processor.handle_forward_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message, correlation_id=correlation_id, interaction_id=interaction_id
            )
            return True

        logger.info(
            "forward_skipped_unrecognized",
            extra={
                "cid": correlation_id,
                "has_forward_date": getattr(message, "forward_date", None) is not None,
            },
        )
        await self.response_formatter.safe_reply(
            message,
            "This forwarded message has no text content to summarize. "
            "Please forward a message that contains text.",
        )
        if interaction_id:
            await async_safe_update_user_interaction(
                self.user_repo,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="forward_no_text",
                start_time=start_time,
                logger_=logger,
            )
        return True
