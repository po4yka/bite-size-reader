"""Re-export for backwards compatibility. Real implementation is in streaming.section_assembler."""

from app.adapters.content.streaming.section_assembler import (
    SummarySectionSnapshot,
    SummarySectionStreamAssembler,
)

__all__ = ["SummarySectionSnapshot", "SummarySectionStreamAssembler"]
