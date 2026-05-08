"""Streaming pub/sub primitives for the URL processing pipeline.

Public API re-exported from sub-modules:

- ``StreamHub`` / ``get_stream_hub`` — process-wide pub/sub hub
- ``StreamEvent`` / ``StreamEventKind`` — event envelope and kind discriminator
- ``PhasePayload`` / ``SectionPayload`` / ``DonePayload`` / ``ErrorPayload`` — payload models
- ``SummarySectionSnapshot`` / ``SummarySectionStreamAssembler`` — incremental section assembler
"""

from app.adapters.content.streaming.events import (
    DonePayload,
    ErrorPayload,
    PhasePayload,
    SectionPayload,
    StreamEvent,
    StreamEventKind,
)
from app.adapters.content.streaming.section_assembler import (
    SummarySectionSnapshot,
    SummarySectionStreamAssembler,
)
from app.adapters.content.streaming.stream_hub import (
    StreamHub,
    get_stream_hub,
)

__all__ = [
    "DonePayload",
    "ErrorPayload",
    "PhasePayload",
    "SectionPayload",
    "StreamEvent",
    "StreamEventKind",
    "StreamHub",
    "SummarySectionSnapshot",
    "SummarySectionStreamAssembler",
    "get_stream_hub",
]
