"""Interaction logging and attachment detection helpers for MessageRouter."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.adapters.telegram.message_router")


class MessageRouterInteractionsMixin:
    """Interaction persistence and content type helpers."""

    async def _log_user_interaction(
        self,
        *,
        user_id: int,
        chat_id: int | None = None,
        message_id: int | None = None,
        interaction_type: str,
        command: str | None = None,
        input_text: str | None = None,
        input_url: str | None = None,
        has_forward: bool = False,
        forward_from_chat_id: int | None = None,
        forward_from_chat_title: str | None = None,
        forward_from_message_id: int | None = None,
        media_type: str | None = None,
        correlation_id: str | None = None,
    ) -> int:
        """Log a user interaction and return the interaction ID."""

        try:
            return await self.user_repo.async_insert_user_interaction(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=input_text,
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                correlation_id=correlation_id,
                structured_output_enabled=self.cfg.openrouter.enable_structured_outputs,
            )
        except Exception as exc:
            logger.warning(
                "user_interaction_log_failed",
                extra={
                    "error": str(exc),
                    "user_id": user_id,
                    "interaction_type": interaction_type,
                    "cid": correlation_id,
                },
            )
            return 0

    @staticmethod
    def _should_handle_attachment(message: Any) -> bool:
        """Check if the message contains a supported attachment (image or PDF)."""
        if getattr(message, "photo", None):
            return True
        doc = getattr(message, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or ""
            if mime.startswith("image/") or mime == "application/pdf":
                return True
        return False
