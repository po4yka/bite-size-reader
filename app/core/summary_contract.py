from __future__ import annotations

from typing import Any

from app.core.summary_contract_impl.contract import (
    _cap_text,
    _extract_keywords_tfidf,
    _normalize_whitespace,
    get_summary_json_schema,
    validate_and_shape_summary,
)
from app.types.summary_types import (
    Entities,
    KeyStat,
    Metadata,
    Readability,
    SemanticChunk,
    SummaryDict,
)

# Legacy alias for backward compatibility
SummaryJSON = dict[str, Any]

# Re-export typed versions for stricter typing
__all__ = [
    "Entities",
    "KeyStat",
    "Metadata",
    "Readability",
    "SemanticChunk",
    "SummaryDict",
    "SummaryJSON",
    "_cap_text",
    "_extract_keywords_tfidf",
    "_normalize_whitespace",
    "get_summary_json_schema",
    "validate_and_shape_summary",
]
