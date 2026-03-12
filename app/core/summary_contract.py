from __future__ import annotations

from typing import Any

from app.core.summary_contract_impl.contract import (
    _cap_text,
    _extract_keywords_tfidf,
    _normalize_whitespace,
    get_summary_json_schema,
    validate_and_shape_summary as _validate_python,
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


def validate_and_shape_summary(payload: SummaryJSON) -> SummaryJSON:
    """Validate and shape summary payload.

    Runs the Python validation and shaping pipeline defined in
    ``summary_contract_impl.contract``.
    """

    return _validate_python(payload)


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
