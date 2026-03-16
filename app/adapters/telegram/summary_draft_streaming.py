"""Helpers to stream section previews via Telegram drafts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.content.summary_section_stream_assembler import SummarySectionStreamAssembler
from app.observability.metrics import record_draft_stream_event

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


@dataclass
class SummaryDraftStreamCoordinator:
    """Coordinates token deltas -> section snapshots -> Telegram draft updates."""

    response_formatter: ResponseFormatter
    message: Any
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        self._assembler = SummarySectionStreamAssembler()
        self._section_emit_count = 0
        self._draft_fallback = False

    @property
    def section_emit_count(self) -> int:
        return self._section_emit_count

    async def on_delta(self, delta: str) -> None:
        snapshots = self._assembler.add_delta(delta)
        if not snapshots:
            return

        self._section_emit_count += len(snapshots)
        record_draft_stream_event("section_emit_count", amount=len(snapshots))
        preview = self._assembler.render_preview()
        ok = await self.response_formatter.send_message_draft(self.message, preview)
        if not ok and not self._draft_fallback:
            self._draft_fallback = True
            logger.info(
                "summary_stream_degraded_to_message_path",
                extra={"cid": self.correlation_id},
            )

    async def finalize(self) -> None:
        if self._assembler.sections:
            await self.response_formatter.send_message_draft(
                self.message,
                self._assembler.render_preview(finalizing=True),
                force=True,
            )
        self.response_formatter.clear_message_draft(self.message)
