"""Internal service bundle for response formatting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import (
        DatabasePresenter,
        DataFormatter,
        MessageValidator,
        NotificationFormatter,
        ResponseSender,
        SummaryPresenter,
        TextProcessor,
    )
    from app.core.progress_tracker import ProgressTracker


@dataclass(frozen=True, slots=True)
class FormattingServices:
    """Typed bundle of internal formatter collaborators."""

    sender: ResponseSender
    notifications: NotificationFormatter
    summaries: SummaryPresenter
    database: DatabasePresenter
    validator: MessageValidator
    text_processor: TextProcessor
    data_formatter: DataFormatter
    progress_tracker: ProgressTracker
