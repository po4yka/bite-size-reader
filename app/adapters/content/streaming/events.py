"""Stream event types and payload models for the in-process pub/sub hub.

These primitives carry progress notifications from the URL processing pipeline
to SSE consumers and Telegram draft-edit subscribers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

StreamEventKind = Literal["phase", "section", "done", "error"]


class PhasePayload(BaseModel):
    phase: Literal["extracting", "summarizing", "validating", "persisting", "done"]


class SectionPayload(BaseModel):
    section: str
    content: str
    partial: bool = False


class DonePayload(BaseModel):
    # ``summary_id`` is None when the pipeline ended without producing one.
    summary_id: str | None
    request_id: str


class ErrorPayload(BaseModel):
    code: str
    message: str
    correlation_id: str


_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "phase": PhasePayload,
    "section": SectionPayload,
    "done": DonePayload,
    "error": ErrorPayload,
}


@dataclass(slots=True, frozen=True)
class StreamEvent:
    kind: StreamEventKind
    payload: dict[str, Any]
    timestamp: datetime
    correlation_id: str

    @classmethod
    def now(
        cls,
        kind: StreamEventKind,
        payload: BaseModel | dict[str, Any],
        correlation_id: str,
    ) -> StreamEvent:
        model_cls = _PAYLOAD_MODELS[kind]
        raw = payload.model_dump() if isinstance(payload, BaseModel) else payload
        validated = model_cls.model_validate(raw)
        return cls(
            kind=kind,
            payload=validated.model_dump(),
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id,
        )


__all__ = [
    "DonePayload",
    "ErrorPayload",
    "PhasePayload",
    "SectionPayload",
    "StreamEvent",
    "StreamEventKind",
]
