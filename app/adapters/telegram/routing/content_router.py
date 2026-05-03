"""Content routing for prepared Telegram message contexts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.ui_strings import t
from app.core.url_utils import extract_all_urls, looks_like_url

if TYPE_CHECKING:
    from app.adapters.attachment.attachment_processor import AttachmentProcessor
    from app.adapters.external.formatting.protocols import (
        ResponseFormatterFacade as ResponseFormatter,
    )
    from app.adapters.telegram.callback_handler import CallbackHandler
    from app.adapters.telegram.command_dispatcher import TelegramCommandDispatcher
    from app.adapters.telegram.forward_processor import ForwardProcessor
    from app.adapters.telegram.multi_source_aggregation_handler import (
        MultiSourceAggregationHandler,
    )
    from app.adapters.telegram.url_handler import URLHandler

    from .interactions import MessageInteractionRecorder
    from .models import PreparedRouteContext

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageContentRouter:
    """Route prepared message contexts to explicit collaborators."""

    def __init__(
        self,
        *,
        command_dispatcher: TelegramCommandDispatcher,
        url_handler: URLHandler,
        forward_processor: ForwardProcessor,
        response_formatter: ResponseFormatter,
        interaction_recorder: MessageInteractionRecorder,
        callback_handler: CallbackHandler | None = None,
        attachment_processor: AttachmentProcessor | None = None,
        aggregation_handler: MultiSourceAggregationHandler | None = None,
        lang: str = "en",
        aggregation_default_mode: str = "per_url",
    ) -> None:
        self.command_dispatcher = command_dispatcher
        self.url_handler = url_handler
        self.forward_processor = forward_processor
        self.response_formatter = response_formatter
        self.interaction_recorder = interaction_recorder
        self.callback_handler = callback_handler
        self.attachment_processor = attachment_processor
        self.aggregation_handler = aggregation_handler
        self._lang = lang
        self._aggregation_default_mode = aggregation_default_mode

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
        ) and self.command_dispatcher.has_active_init_session(context.uid):
            await self.command_dispatcher.handle_init_session_contact(context.message)
            return

        if getattr(
            context.message,
            "web_app_data",
            None,
        ) and self.command_dispatcher.has_active_init_session(context.uid):
            await self.command_dispatcher.handle_init_session_webapp(context.message)
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

        if (
            context.text
            and self.aggregation_handler is not None
            and self._aggregation_default_mode == "bundle"
        ):
            url_count = len(extract_all_urls(context.text))
            if url_count >= 2:
                handled = await self.aggregation_handler.handle_message_bundle(
                    message=context.message,
                    text=context.text,
                    uid=context.uid,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                if handled:
                    return

        if (
            self.aggregation_handler is not None
            and self._should_handle_attachment(context.message)
            and extract_all_urls(context.text)
        ):
            handled = await self.aggregation_handler.handle_message_bundle(
                message=context.message,
                text=context.text,
                uid=context.uid,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            if handled:
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
        outcome = await self.command_dispatcher.dispatch_command(
            message=context.message,
            text=context.text,
            uid=context.uid,
            correlation_id=context.correlation_id,
            interaction_id=interaction_id,
            start_time=start_time,
        )
        return outcome.handled

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
        forwarded_urls = extract_all_urls(fwd_text)
        has_supported_attachment = self.attachment_processor and self._should_handle_attachment(
            message
        )

        if fwd_chat is not None and fwd_msg_id is not None:
            if self.aggregation_handler is not None and forwarded_urls:
                handled = await self.aggregation_handler.handle_message_bundle(
                    message=message,
                    text=fwd_text,
                    uid=context.uid,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                if handled:
                    return
            if has_supported_attachment:
                await self.attachment_processor.handle_attachment_flow(
                    message,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                return
            await self.forward_processor.handle_forward_flow(
                message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        if fwd_from_user is not None or fwd_sender_name:
            if self.aggregation_handler is not None and forwarded_urls:
                handled = await self.aggregation_handler.handle_message_bundle(
                    message=message,
                    text=fwd_text,
                    uid=context.uid,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                if handled:
                    return
            if has_supported_attachment:
                await self.attachment_processor.handle_attachment_flow(
                    message,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                return
            if fwd_text:
                await self.forward_processor.handle_forward_flow(
                    message,
                    correlation_id=context.correlation_id,
                    interaction_id=interaction_id,
                )
                return
            await self._reply_forward_no_text(context, interaction_id, start_time)
            return

        if self.aggregation_handler is not None and forwarded_urls:
            handled = await self.aggregation_handler.handle_message_bundle(
                message=message,
                text=fwd_text,
                uid=context.uid,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            if handled:
                return

        if has_supported_attachment:
            await self.attachment_processor.handle_attachment_flow(
                message,
                correlation_id=context.correlation_id,
                interaction_id=interaction_id,
            )
            return

        if fwd_text:
            await self.forward_processor.handle_forward_flow(
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

    _DOCUMENT_MIME_TYPES: frozenset[str] = frozenset({
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/epub+zip",
        "application/rtf",
        "text/rtf",
        "text/csv",
        "text/html",
        "application/json",
        "application/xml",
        "text/xml",
    })

    @classmethod
    def _should_handle_attachment(cls, message: Any) -> bool:
        if getattr(message, "photo", None):
            return True
        document = getattr(message, "document", None)
        if document:
            mime = getattr(document, "mime_type", "") or ""
            if mime.startswith("image/") or mime == "application/pdf":
                return True
            if mime in cls._DOCUMENT_MIME_TYPES:
                return True
        return False
