"""Shared context for notification formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import DataFormatter, ResponseSender
    from app.core.telegram_progress_message import TelegramProgressMessage
    from app.core.verbosity import VerbosityResolver


@dataclass(slots=True)
class NotificationFormatterContext:
    """Mutable collaborator bundle for notification helper modules."""

    response_sender: ResponseSender
    data_formatter: DataFormatter
    verbosity_resolver: VerbosityResolver | None
    progress_tracker: TelegramProgressMessage | None
    lang: str
    notified_error_ids: set[str] = field(default_factory=set)
