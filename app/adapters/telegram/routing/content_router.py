"""Content routing for prepared Telegram message contexts."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from app.core.ui_strings import t
from app.core.url_utils import looks_like_url

if TYPE_CHECKING:
    from app.adapters.attachment.attachment_processor import AttachmentProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.callback_handler import CallbackHandler
    from app.adapters.telegram.command_processor import CommandProcessor
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.url_handler import URLHandler

    from .interactions import MessageInteractionRecorder
    from .models import PreparedRouteContext

logger = logging.getLogger("app.adapters.telegram.message_router")

UidCommandHandler = Callable[[Any, int, str, int, float], Awaitable[None]]
TextCommandHandler = Callable[[Any, str, int, str, int, float], Awaitable[None]]
AliasCommandHandler = Callable[..., Awaitable[None]]

_LOCAL_SEARCH_ALIASES: tuple[str, ...] = ("/finddb", "/findlocal")
_ONLINE_SEARCH_ALIASES: tuple[str, ...] = ("/findweb", "/findonline", "/find")


class MessageContentRouter:
    """Route prepared message contexts to explicit collaborators."""

    def __init__(
        self,
        *,
        command_processor: CommandProcessor,
        url_handler: URLHandler,
        forward_processor: ForwardProcessor,
        response_formatter: ResponseFormatter,
        interaction_recorder: MessageInteractionRecorder,
        callback_handler: CallbackHandler | None = None,
        attachment_processor: AttachmentProcessor | None = None,
        lang: str = "en",
    ) -> None:
        self.command_processor = command_processor
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.response_formatter = response_formatter
        self.interaction_recorder = interaction_recorder
        self.callback_handler = callback_handler
        self.attachment_processor = attachment_processor
        self._lang = lang

        self._pre_alias_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/start", command_processor.handle_start_command),
            ("/help", command_processor.handle_help_command),
            ("/dbinfo", command_processor.handle_dbinfo_command),
            ("/dbverify", command_processor.handle_dbverify_command),
            ("/clearcache", command_processor.handle_clearcache_command),
        )
        self._pre_summarize_text_commands: tuple[tuple[str, TextCommandHandler], ...] = (
            ("/summarize_all", command_processor.handle_summarize_all_command),
        )
        self._post_summarize_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/cancel", command_processor.handle_cancel_command),
        )
        self._post_summarize_text_commands: tuple[tuple[str, TextCommandHandler], ...] = (
            ("/unread", command_processor.handle_unread_command),
            ("/read", command_processor.handle_read_command),
            ("/search", command_processor.handle_search_command),
            ("/sync_karakeep", command_processor.handle_sync_karakeep_command),
            ("/listen", command_processor.handle_listen_command),
            ("/cdigest", command_processor.handle_cdigest_command),
            ("/digest", command_processor.handle_digest_command),
            ("/channels", command_processor.handle_channels_command),
            ("/subscribe", command_processor.handle_subscribe_command),
            ("/unsubscribe", command_processor.handle_unsubscribe_command),
            ("/init_session", command_processor.handle_init_session_command),
            ("/settings", command_processor.handle_settings_command),
        )
        self._tail_uid_commands: tuple[tuple[str, UidCommandHandler], ...] = (
            ("/debug", command_processor.handle_debug_command),
        )

    async def route(
        self,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> None:
        """Route a prepared context according to the existing precedence rules."""
        if context.text.startswith("/") and self.callback_handler is not None:
            try:
                if await self.callback_handler.has_pending_followup(context.uid):
                    await self.callback_handler.clear_pending_followup(context.uid)
            except Exception as exc:
                logger.warning("followup_clear_on_command_failed", extra={"error": str(exc)})

        if getattr(
            context.message, "contact", None
        ) and self.command_processor.has_active_init_session(context.uid):
            await self.command_processor.handle_init_session_contact(context.message)
            return

        if getattr(
            context.message,
            "web_app_data",
            None,
        ) and self.command_processor.has_active_init_session(context.uid):
            await self.command_processor.handle_init_session_webapp(context.message)
            return

        if await self._route_command_message(context, interaction_id, start_time):
            return

        if context.has_forward:
            await self._route_forward_message(context, interaction_id, start_time)
            return

        if self.callback_handler is not None and context.text and not context.text.startswith("/"):
            try:
                if await self.callback_handler.handle_followup_question(
                    message=context.message,
                    uid=context.uid,
                    question=context.text,
                    correlation_id=context.correlation_id,
                ):
                    return
            except Exception as exc:
                logger.exception(
                    "followup_question_route_failed",
                    extra={"uid": context.uid, "cid": context.correlation_id, "error": str(exc)},
                )

        if await self.url_handler.is_awaiting_url(context.uid) and looks_like_url(context.text):
            await self.url_handler.handle_awaited_url(
                context.message,
                context.text,
                context.uid,
                context.correlation_id,
                interaction_id,
                start_time,
            )
            return

        if context.text and looks_like_url(context.text):
            await self.url_handler.handle_direct_url(
                context.message,
                context.text,
                context.uid,
                context.correlation_id,
                interaction_id,
                start_time,
            )
            return

        if self.url_handler.can_handle_document(context.message):
            await self.url_handler.handle_document_file(
                context.message,
                context.correlation_id,
                interaction_id,
                start_time,
            )
            return

        if self.attachment_processor and self._should_handle_attachment(context.message):
            await self.attachment_processor.handle_attachment_flow(
                context.message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        await self.response_formatter.safe_reply(context.message, t("fallback_prompt", self._lang))
        logger.debug(
            "unknown_input",
            extra={
                "has_forward": bool(getattr(context.message, "forward_from_chat", None)),
                "text_len": len(context.text),
            },
        )
        await self.interaction_recorder.update(
            interaction_id,
            response_sent=True,
            response_type="unknown_input",
            start_time=start_time,
        )

    async def _route_command_message(
        self,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        if not context.text.startswith("/"):
            return False

        if await self._dispatch_uid_command(
            context.text,
            self._pre_alias_uid_commands,
            context,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_alias_command(
            context.text,
            _LOCAL_SEARCH_ALIASES,
            self.command_processor.handle_find_local_command,
            context,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_alias_command(
            context.text,
            _ONLINE_SEARCH_ALIASES,
            self.command_processor.handle_find_online_command,
            context,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_text_command(
            context.text,
            self._pre_summarize_text_commands,
            context,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_summarize_command(context, interaction_id, start_time):
            return True

        if await self._dispatch_uid_command(
            context.text,
            self._post_summarize_uid_commands,
            context,
            interaction_id,
            start_time,
        ):
            return True

        if await self._dispatch_text_command(
            context.text,
            self._post_summarize_text_commands,
            context,
            interaction_id,
            start_time,
        ):
            return True

        return await self._dispatch_uid_command(
            context.text,
            self._tail_uid_commands,
            context,
            interaction_id,
            start_time,
        )

    async def _dispatch_uid_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, UidCommandHandler], ...],
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        for prefix, handler in handlers:
            if route_probe.startswith(prefix):
                await handler(
                    context.message,
                    context.uid,
                    context.correlation_id,
                    interaction_id,
                    start_time,
                )
                return True
        return False

    async def _dispatch_text_command(
        self,
        route_probe: str,
        handlers: tuple[tuple[str, TextCommandHandler], ...],
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        for prefix, handler in handlers:
            if route_probe.startswith(prefix):
                await handler(
                    context.message,
                    context.text,
                    context.uid,
                    context.correlation_id,
                    interaction_id,
                    start_time,
                )
                return True
        return False

    async def _dispatch_alias_command(
        self,
        route_probe: str,
        aliases: tuple[str, ...],
        handler: AliasCommandHandler,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        matched_alias = self._match_prefix(route_probe, aliases)
        if matched_alias is None:
            return False

        await handler(
            context.message,
            context.text,
            context.uid,
            context.correlation_id,
            interaction_id,
            start_time,
            command=matched_alias,
        )
        return True

    async def _dispatch_summarize_command(
        self,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> bool:
        if not context.text.startswith("/summarize"):
            return False

        action, _should_continue = await self.command_processor.handle_summarize_command(
            context.message,
            context.text,
            context.uid,
            context.correlation_id,
            interaction_id,
            start_time,
        )
        if action == "awaiting_url":
            await self.url_handler.add_awaiting_user(context.uid)
        return True

    async def _route_forward_message(
        self,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> None:
        message = context.message
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_msg_id = getattr(message, "forward_from_message_id", None)
        fwd_from_user = getattr(message, "forward_from", None)
        fwd_sender_name = getattr(message, "forward_sender_name", None)
        fwd_text = (
            getattr(message, "text", None) or getattr(message, "caption", None) or ""
        ).strip()

        if fwd_chat is not None and fwd_msg_id is not None:
            await self.forward_processor.handle_forward_flow(
                message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        if fwd_from_user is not None or fwd_sender_name:
            if fwd_text:
                await self.forward_processor.handle_forward_flow(
                    message,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                return
            if self.attachment_processor and self._should_handle_attachment(message):
                await self.attachment_processor.handle_attachment_flow(
                    message,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                return
            await self._reply_forward_no_text(context, interaction_id, start_time)
            return

        if fwd_text:
            await self.forward_processor.handle_forward_flow(
                message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        if self.attachment_processor and self._should_handle_attachment(message):
            await self.attachment_processor.handle_attachment_flow(
                message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        logger.info(
            "forward_skipped_unrecognized",
            extra={
                "cid": context.correlation_id,
                "has_forward_date": getattr(message, "forward_date", None) is not None,
            },
        )
        await self._reply_forward_no_text(context, interaction_id, start_time)

    async def _reply_forward_no_text(
        self,
        context: PreparedRouteContext,
        interaction_id: int,
        start_time: float,
    ) -> None:
        logger.info(
            "forward_skipped_no_text",
            extra={
                "cid": context.correlation_id,
                "has_fwd_user": getattr(context.message, "forward_from", None) is not None,
                "has_fwd_sender_name": bool(getattr(context.message, "forward_sender_name", None)),
            },
        )
        await self.response_formatter.safe_reply(
            context.message,
            "This forwarded message has no text content to summarize. "
            "Please forward a message that contains text.",
        )
        await self.interaction_recorder.update(
            interaction_id,
            response_sent=True,
            response_type="forward_no_text",
            start_time=start_time,
        )

    @staticmethod
    def _match_prefix(text: str, prefixes: tuple[str, ...]) -> str | None:
        for prefix in prefixes:
            if text.startswith(prefix):
                return prefix
        return None

    @staticmethod
    def _should_handle_attachment(message: Any) -> bool:
        if getattr(message, "photo", None):
            return True
        document = getattr(message, "document", None)
        if document:
            mime = getattr(document, "mime_type", "") or ""
            if mime.startswith("image/") or mime == "application/pdf":
                return True
        return False
