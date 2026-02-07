"""URL processing command handlers (/summarize, /summarize_all, /cancel).

This module handles commands related to URL summarization workflow,
including single URL processing, batch processing, and cancellation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.command_handlers.decorators import audit_command
from app.core.logging_utils import generate_correlation_id
from app.core.url_utils import extract_all_urls
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.content.url_processor import URLProcessor
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.telegram.command_handlers.execution_context import (
        CommandExecutionContext,
    )
    from app.adapters.telegram.task_manager import UserTaskManager
    from app.adapters.telegram.url_handler import URLHandler

logger = logging.getLogger(__name__)


class URLCommandsHandlerImpl:
    """Implementation of URL processing commands.

    Handles /summarize, /summarize_all, and /cancel commands which control
    the URL summarization workflow.
    """

    def __init__(
        self,
        response_formatter: ResponseFormatter,
        processor_provider: Any,
    ) -> None:
        """Initialize the URL commands handler.

        Args:
            response_formatter: Response formatter for sending messages.
            processor_provider: Object with url_processor, url_handler, and
                _task_manager attributes that can be dynamically accessed.
                This allows tests to modify these after initialization.
        """
        self._formatter = response_formatter
        self._processor_provider = processor_provider

    @property
    def _url_processor(self) -> URLProcessor:
        """Get the current URL processor from the provider."""
        return self._processor_provider.url_processor

    @property
    def _url_handler(self) -> URLHandler | None:
        """Get the current URL handler from the provider."""
        return getattr(self._processor_provider, "url_handler", None)

    @property
    def _task_manager(self) -> UserTaskManager | None:
        """Get the current task manager from the provider."""
        return getattr(self._processor_provider, "_task_manager", None)

    @audit_command("command_summarize", include_text=True)
    async def handle_summarize(
        self,
        ctx: CommandExecutionContext,
    ) -> tuple[str | None, bool]:
        """Handle /summarize command.

        Processes a URL from the message or prompts the user to send one.
        If multiple URLs are provided, asks for confirmation.

        Args:
            ctx: The command execution context.

        Returns:
            Tuple of (next_action, should_continue) indicating the state machine
            transition. next_action can be:
            - None: Processing complete
            - "multi_confirm": Waiting for multi-link confirmation
            - "awaiting_url": Waiting for user to send a URL
        """
        urls = extract_all_urls(ctx.text)

        if len(urls) > 1:
            # Multiple URLs - ask for confirmation using handler's rich format if available
            if self._url_handler is not None:
                await self._url_handler._request_multi_link_confirmation(
                    ctx.message, ctx.uid, urls, ctx.interaction_id, ctx.start_time
                )
            else:
                # Fallback to simple buttons if no handler
                buttons = [
                    {"text": "✅ Yes", "callback_data": "multi_confirm_yes"},
                    {"text": "❌ No", "callback_data": "multi_confirm_no"},
                ]
                keyboard = self._formatter.create_inline_keyboard(buttons)
                await self._formatter.safe_reply(
                    ctx.message, f"Process {len(urls)} links?", reply_markup=keyboard
                )
            logger.debug("awaiting_multi_confirm", extra={"uid": ctx.uid, "count": len(urls)})

            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="confirmation",
                    start_time=ctx.start_time,
                    logger_=logger,
                )
            return "multi_confirm", False

        if len(urls) == 1:
            # Single URL - process directly
            await self._url_processor.handle_url_flow(
                ctx.message,
                urls[0],
                correlation_id=ctx.correlation_id,
                interaction_id=ctx.interaction_id,
            )
            return None, False

        # No URL - prompt user
        await self._formatter.safe_reply(ctx.message, "Send a URL to summarize.")
        logger.debug("awaiting_url", extra={"uid": ctx.uid})

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type="awaiting_url",
                start_time=ctx.start_time,
                logger_=logger,
            )
        return "awaiting_url", False

    @audit_command("command_summarize_all", include_text=True)
    async def handle_summarize_all(self, ctx: CommandExecutionContext) -> None:
        """Handle /summarize_all command.

        Processes multiple URLs from the message in sequence.

        Args:
            ctx: The command execution context.
        """
        urls = extract_all_urls(ctx.text)

        if len(urls) == 0:
            await self._formatter.safe_reply(
                ctx.message,
                "Send multiple URLs in one message after /summarize_all, "
                "separated by space or new line.",
            )
            if ctx.interaction_id:
                await async_safe_update_user_interaction(
                    ctx.user_repo,
                    interaction_id=ctx.interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="No URLs found",
                    start_time=ctx.start_time,
                    logger_=logger,
                )
            return

        # Use a single progress message that updates in-place
        progress_message_id = await self._formatter.safe_reply_with_id(
            ctx.message, f"🚀 Preparing to process {len(urls)} links..."
        )

        if ctx.interaction_id:
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type="processing",
                start_time=ctx.start_time,
                logger_=logger,
            )

        # Use unified batch processor if url_handler is available, otherwise sequential
        if self._url_handler is not None:
            await self._url_handler._process_multiple_urls_parallel(
                ctx.message,
                urls,
                ctx.uid,
                ctx.correlation_id,
                initial_message_id=progress_message_id,
            )
        else:
            # Fallback to sequential if handler not available
            for u in urls:
                per_link_cid = generate_correlation_id()
                logger.debug(
                    "processing_link_seq", extra={"uid": ctx.uid, "url": u, "cid": per_link_cid}
                )
                await self._url_processor.handle_url_flow(
                    ctx.message, u, correlation_id=per_link_cid
                )

    @audit_command("command_cancel")
    async def handle_cancel(self, ctx: CommandExecutionContext) -> None:
        """Handle /cancel command.

        Cancels any pending URL requests, multi-link confirmations,
        or active processing tasks.

        Args:
            ctx: The command execution context.
        """
        awaiting_cancelled = False
        multi_cancelled = False
        active_cancelled = 0

        # Cancel pending requests via URL handler
        if self._url_handler is not None:
            awaiting_cancelled, multi_cancelled = await self._url_handler.cancel_pending_requests(
                ctx.uid
            )

        # Cancel active tasks via task manager
        if self._task_manager is not None:
            active_cancelled = await self._task_manager.cancel(ctx.uid, exclude_current=True)

        # Build response message
        cancelled_parts: list[str] = []
        if awaiting_cancelled:
            cancelled_parts.append("pending URL request")
        if multi_cancelled:
            cancelled_parts.append("pending multi-link confirmation")
        if active_cancelled:
            if active_cancelled == 1:
                cancelled_parts.append("ongoing request")
            else:
                cancelled_parts.append(f"{active_cancelled} ongoing requests")

        if cancelled_parts:
            if len(cancelled_parts) == 1:
                detail = cancelled_parts[0]
            else:
                detail = ", ".join(cancelled_parts[:-1]) + f", and {cancelled_parts[-1]}"
            reply_text = f"🛑 Cancelled your {detail}."
        else:
            reply_text = "ℹ️ No pending link requests to cancel."

        await self._formatter.safe_reply(ctx.message, reply_text)

        if ctx.interaction_id:
            response_type = (
                "cancelled"
                if (awaiting_cancelled or multi_cancelled or active_cancelled)
                else "cancel_none"
            )
            await async_safe_update_user_interaction(
                ctx.user_repo,
                interaction_id=ctx.interaction_id,
                response_sent=True,
                response_type=response_type,
                start_time=ctx.start_time,
                logger_=logger,
            )
