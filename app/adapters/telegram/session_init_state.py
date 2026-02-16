"""In-memory state for the bot-mediated userbot session initialization flow."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

# 5-minute TTL for session init flow
SESSION_INIT_TTL_SECONDS = 300


@dataclass
class SessionInitState:
    """Ephemeral per-user state for the /init_session multi-step flow.

    Tracked in-memory only (not persisted to DB). Cleaned up on completion,
    error, or after SESSION_INIT_TTL_SECONDS.
    """

    phone_number: str = ""
    phone_code_hash: str = ""
    client: Any = None  # pyrogram.Client (unauthenticated)
    message_ids: list[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    step: Literal["waiting_contact", "waiting_otp", "waiting_2fa"] = "waiting_contact"

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > SESSION_INIT_TTL_SECONDS
