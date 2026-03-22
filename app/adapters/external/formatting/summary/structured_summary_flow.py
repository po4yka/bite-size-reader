"""Structured summary and forward-summary orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.adapters.external.formatting.summary.action_buttons import create_inline_keyboard
from app.adapters.external.formatting.summary.card_renderer import build_compact_card_html
from app.adapters.external.formatting.summary.crosspost_publisher import crosspost_to_topic
from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger
from app.core.ui_strings import t

if TYPE_CHECKING:
    from .presenter_context import SummaryPresenterContext
    from .summary_blocks import SummaryBlocksPresenter

logger = get_logger(__name__)


class StructuredSummaryFlow:
    """Handle structured-summary and forward-summary delivery."""

    def __init__(
        self,
        context: SummaryPresenterContext,
        *,
        blocks: SummaryBlocksPresenter,
    ) -> None:
        self._context = context
        self._blocks = blocks

    def _build_compact_card_html(
        self, summary_shaped: dict[str, Any], llm: Any, chunks: int | None, *, reader: bool
    ) -> str:
        return build_compact_card_html(
            summary_shaped,
            llm,
            chunks,
            reader=reader,
            text_processor=self._context.text_processor,
            data_formatter=self._context.data_formatter,
            lang=self._context.lang,
        )

    def _create_inline_keyboard(
        self, summary_id: int | str, correlation_id: str | None = None
    ) -> Any:
        return create_inline_keyboard(summary_id, correlation_id, lang=self._context.lang)

    async def _send_action_buttons(
        self, message: Any, summary_id: int | str, correlation_id: str | None = None
    ) -> int | None:
        try:
            keyboard = self._create_inline_keyboard(summary_id, correlation_id)
            if keyboard:
                msg_id = await self._context.response_sender.safe_reply_with_id(
                    message,
                    t("quick_actions", self._context.lang),
                    reply_markup=keyboard,
                )
                logger.debug("action_buttons_sent", extra={"summary_id": summary_id})
                return msg_id
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "send_action_buttons_failed",
                extra={"summary_id": summary_id, "error": str(exc)},
            )
        return None

    async def _is_reader_mode(self, message: Any) -> bool:
        if self._context.verbosity_resolver is None:
            return False
        from app.core.verbosity import VerbosityLevel

        return (
            await self._context.verbosity_resolver.get_verbosity(message)
        ) == VerbosityLevel.READER

    async def _finalize_compact_card(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None,
        summary_id: int | str | None,
        *,
        reader: bool,
    ) -> tuple[bool, str | None]:
        card_text: str | None = None
        try:
            card_text = self._build_compact_card_html(summary_shaped, llm, chunks, reader=reader)
            if self._context.progress_tracker is None:
                return False, card_text

            keyboard = self._create_inline_keyboard(summary_id) if summary_id else None
            result = await self._context.progress_tracker.finalize(
                message,
                card_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            if result is not None:
                return True, card_text
            logger.warning(
                "progress_finalize_failed_fallback",
                extra={"request_message_id": getattr(message, "id", None)},
            )
        except Exception as exc:
            raise_if_cancelled(exc)
            logger.warning(
                "compact_card_build_failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "request_message_id": getattr(message, "id", None),
                },
            )
        return False, card_text

    async def _send_structured_header(self, message: Any, llm: Any, chunks: int | None) -> None:
        method = (
            f"{t('chunked', self._context.lang)} ({chunks} parts)"
            if chunks
            else t("single_pass", self._context.lang)
        )
        model_name = getattr(llm, "model", None)
        header = (
            f"{t('summary_ready', self._context.lang)}\n"
            f"{t('model', self._context.lang)}: {model_name or 'unknown'}\n"
            f"Method: {method}"
        )
        await self._context.response_sender.safe_reply(message, header)

    async def send_structured_summary_response(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None = None,
        summary_id: int | str | None = None,
        correlation_id: str | None = None,
    ) -> int | None:
        try:
            reader = await self._is_reader_mode(message)
            job_card_finalized, card_text = await self._finalize_compact_card(
                message,
                summary_shaped,
                llm,
                chunks,
                summary_id,
                reader=reader,
            )

            if reader and job_card_finalized:
                return None

            if not reader and not job_card_finalized:
                try:
                    await self._send_structured_header(message, llm, chunks)
                except Exception as exc:
                    raise_if_cancelled(exc)

            if not job_card_finalized:
                await self._blocks.send_combined_summary_lines(
                    message, summary_shaped, include_domain=True
                )

            await self._blocks.send_summary_fields(
                message,
                summary_shaped,
                include_tldr=not job_card_finalized,
            )
            await self._blocks.send_key_ideas(message, summary_shaped)
            await self._blocks.send_new_field_messages(message, summary_shaped)
            await self._context.response_sender.reply_json(message, summary_shaped)

            bot_reply_id: int | None = None
            if summary_id and not job_card_finalized:
                bot_reply_id = await self._send_action_buttons(message, summary_id, correlation_id)

            await self._crosspost_to_topic(
                message,
                summary_shaped,
                llm,
                chunks,
                summary_id,
                correlation_id,
                card_text,
            )
            return bot_reply_id
        except Exception as exc:
            raise_if_cancelled(exc)
            try:
                tl_dr = str(summary_shaped.get("summary_250", "")).strip()
                if tl_dr:
                    await self._context.response_sender.safe_reply(message, f"📋 TL;DR:\n{tl_dr}")
            except Exception as exc2:
                raise_if_cancelled(exc2)

            await self._context.response_sender.reply_json(message, summary_shaped)
            if summary_id:
                await self._send_action_buttons(message, summary_id, correlation_id)
            return None

    async def send_forward_summary_response(
        self, message: Any, forward_shaped: dict[str, Any], summary_id: int | str | None = None
    ) -> None:
        try:
            _l = self._context.lang
            if self._context.progress_tracker is not None:
                result = await self._context.progress_tracker.finalize(
                    message, t("forward_summary_ready", _l)
                )
                if result is None:
                    logger.warning(
                        "forward_progress_finalize_failed",
                        extra={"request_message_id": getattr(message, "id", None)},
                    )
            else:
                await self._context.response_sender.safe_reply(
                    message, t("forward_summary_ready", _l)
                )

            await self._blocks.send_combined_summary_lines(
                message, forward_shaped, include_domain=False
            )
            await self._blocks.send_summary_fields(message, forward_shaped, include_tldr=False)
            await self._blocks.send_key_ideas(message, forward_shaped)
            await self._blocks.send_new_field_messages(message, forward_shaped)
        except Exception as exc:
            raise_if_cancelled(exc)

        await self._context.response_sender.reply_json(message, forward_shaped)
        if summary_id:
            await self._send_action_buttons(message, summary_id)

    async def _crosspost_to_topic(
        self,
        message: Any,
        summary_shaped: dict[str, Any],
        llm: Any,
        chunks: int | None,
        summary_id: int | str | None,
        correlation_id: str | None,
        card_text: str | None = None,
    ) -> None:
        if self._context.topic_manager is None:
            return
        if card_text is None:
            card_text = self._build_compact_card_html(summary_shaped, llm, chunks, reader=True)
        await crosspost_to_topic(
            topic_manager=self._context.topic_manager,
            response_sender=self._context.response_sender,
            message=message,
            summary_shaped=summary_shaped,
            summary_id=summary_id,
            correlation_id=correlation_id,
            card_text=card_text,
            create_keyboard_fn=self._create_inline_keyboard,
        )
