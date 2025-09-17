"""Refactored forward processor using modular components."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.telegram.forward_content_processor import ForwardContentProcessor
from app.adapters.telegram.forward_summarizer import ForwardSummarizer
from app.config import AppConfig
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient


class ForwardProcessor:
    """Refactored forward processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter

        # Initialize components
        self.content_processor = ForwardContentProcessor(
            cfg=cfg,
            db=db,
            response_formatter=response_formatter,
            audit_func=audit_func,
        )

        self.summarizer = ForwardSummarizer(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

    async def handle_forward_flow(
        self, message: Any, *, correlation_id: str | None = None, interaction_id: int | None = None
    ) -> None:
        """Handle complete forwarded message processing flow."""
        try:
            # Process forward content
            (
                req_id,
                prompt,
                chosen_lang,
                system_prompt,
            ) = await self.content_processor.process_forward_content(message, correlation_id)

            # Summarize content
            forward_shaped = await self.summarizer.summarize_forward(
                message, prompt, chosen_lang, system_prompt, req_id, correlation_id, interaction_id
            )

            if forward_shaped:
                # Send enhanced preview for forward flow
                await self.response_formatter.send_forward_summary_response(message, forward_shaped)

        except Exception as e:
            # Handle unexpected errors
            import logging

            logger = logging.getLogger(__name__)
            logger.exception("forward_flow_error", extra={"error": str(e), "cid": correlation_id})
