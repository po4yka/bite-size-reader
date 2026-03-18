"""Telegram sendMessageDraft transport with per-request fallback handling."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from app.core.async_utils import raise_if_cancelled
from app.core.logging_utils import get_logger
from app.observability.metrics import record_draft_stream_event

logger = get_logger(__name__)


@dataclass(frozen=True)
class DraftStreamSettings:
    """Configuration for draft streaming throttling and limits."""

    enabled: bool = True
    min_interval_ms: int = 700
    min_delta_chars: int = 40
    max_chars: int = 3500


@dataclass
class DraftStreamState:
    """Mutable state for a single request-level draft stream."""

    last_text: str = ""
    last_sent_monotonic: float = 0.0
    fallback: bool = False
    fallback_reason: str | None = None


@dataclass(frozen=True)
class DraftSendResult:
    """Result of a draft update attempt."""

    ok: bool
    sent: bool
    fallback: bool
    reason: str | None = None


class DraftStreamSender:
    """Sends Telegram draft updates via raw SendCustomRequest transport."""

    def __init__(
        self,
        *,
        telegram_client: Any,
        settings: DraftStreamSettings,
    ) -> None:
        self._telegram_client = telegram_client
        self._settings = settings
        self._states: dict[tuple[int, int], DraftStreamState] = {}

    def set_telegram_client(self, telegram_client: Any) -> None:
        """Update Telegram client reference (used by ResponseFormatter rewiring)."""
        self._telegram_client = telegram_client

    @property
    def enabled(self) -> bool:
        return bool(self._settings.enabled)

    def clear(self, message: Any) -> None:
        """Clear tracked draft state for the message key."""
        key = self.request_key(message)
        if key is not None:
            self._states.pop(key, None)

    def request_key(self, message: Any) -> tuple[int, int] | None:
        """Build request key from incoming message for per-request stream state."""
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)
        trigger_message_id = getattr(message, "id", None) or getattr(message, "message_id", None)
        if chat_id is None or trigger_message_id is None:
            return None
        return int(chat_id), int(trigger_message_id)

    async def send_update(
        self,
        message: Any,
        text: str,
        *,
        message_thread_id: int | None = None,
        force: bool = False,
    ) -> DraftSendResult:
        """Send one draft update with strict fallback-once semantics."""
        if not self._settings.enabled:
            return DraftSendResult(ok=False, sent=False, fallback=True, reason="disabled")

        key = self.request_key(message)
        if key is None:
            return DraftSendResult(
                ok=False, sent=False, fallback=True, reason="missing_request_key"
            )

        state = self._states.setdefault(key, DraftStreamState())
        if state.fallback:
            return DraftSendResult(
                ok=False,
                sent=False,
                fallback=True,
                reason=state.fallback_reason or "draft_disabled_for_request",
            )

        normalized = self._normalize_text(text)
        if not normalized:
            return DraftSendResult(ok=True, sent=False, fallback=False, reason="empty_text")

        if not force and self._is_throttled(state, normalized):
            return DraftSendResult(ok=True, sent=False, fallback=False, reason="throttled")

        chat_id, _ = key
        params: dict[str, Any] = {"chat_id": chat_id, "text": normalized}
        if message_thread_id is not None:
            params["message_thread_id"] = int(message_thread_id)

        record_draft_stream_event("draft_send_attempt")
        logger.debug(
            "draft_send_attempt",
            extra={
                "chat_id": chat_id,
                "message_thread_id": message_thread_id,
                "length": len(normalized),
            },
        )

        try:
            await self._send_custom_request(params)
            state.last_text = normalized
            state.last_sent_monotonic = time.monotonic()
            record_draft_stream_event("draft_send_success")
            logger.debug(
                "draft_send_success",
                extra={"chat_id": chat_id, "length": len(normalized)},
            )
            return DraftSendResult(ok=True, sent=True, fallback=False)
        except Exception as exc:
            raise_if_cancelled(exc)
            reason = self._classify_failure_reason(exc)
            state.fallback = True
            state.fallback_reason = reason
            record_draft_stream_event("draft_send_fallback")
            if reason == "policy_reject":
                record_draft_stream_event("draft_send_policy_reject")
            logger.warning(
                "draft_send_fallback",
                extra={
                    "chat_id": chat_id,
                    "reason": reason,
                    "error": str(exc),
                },
            )
            return DraftSendResult(ok=False, sent=False, fallback=True, reason=reason)

    def _normalize_text(self, text: str) -> str:
        normalized = (text or "").strip()
        if not normalized:
            return ""
        if len(normalized) > self._settings.max_chars:
            return normalized[: self._settings.max_chars - 1].rstrip() + "…"
        return normalized

    def _is_throttled(self, state: DraftStreamState, text: str) -> bool:
        if state.last_sent_monotonic <= 0:
            return False
        now = time.monotonic()
        elapsed_ms = (now - state.last_sent_monotonic) * 1000.0
        chars_delta = abs(len(text) - len(state.last_text))
        return text == state.last_text or (
            elapsed_ms < self._settings.min_interval_ms
            and chars_delta < self._settings.min_delta_chars
        )

    async def _send_custom_request(self, params: dict[str, Any]) -> None:
        client = getattr(self._telegram_client, "client", None)
        if client is None or not hasattr(client, "invoke"):
            msg = "telegram_client_invoke_unavailable"
            raise RuntimeError(msg)

        from pyrogram.raw.functions.bots import SendCustomRequest
        from pyrogram.raw.types import DataJSON

        payload = json.dumps(params, ensure_ascii=False)
        request = SendCustomRequest(
            custom_method="sendMessageDraft",
            params=DataJSON(data=payload),
        )
        await client.invoke(request)

    @staticmethod
    def _classify_failure_reason(exc: Exception) -> str:
        error_text = str(exc).lower()
        policy_markers = (
            "not enough stars",
            "stars",
            "fee",
            "payment",
            "premium",
            "policy",
            "forbidden",
        )
        unsupported_markers = (
            "unknown method",
            "method not found",
            "sendmessagedraft",
            "not implemented",
        )
        if any(marker in error_text for marker in policy_markers):
            return "policy_reject"
        if any(marker in error_text for marker in unsupported_markers):
            return "unsupported"
        return "transport_error"
