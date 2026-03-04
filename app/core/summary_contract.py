from __future__ import annotations

from typing import Any

from app.core.summary_contract_impl.contract import (
    _cap_text,
    _extract_keywords_tfidf,
    _normalize_whitespace,
    get_summary_json_schema,
)
from app.core.summary_contract_impl.rust_backend import validate_with_backend
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
    """Validate and shape summary payload via configured backend.

    Backend selection:
    - ``SUMMARY_CONTRACT_BACKEND=rust`` (default): Rust implementation (required)
    - Legacy values are ignored and routed to Rust.
    - Python fallback for this slice is decommissioned.
    """

    return validate_with_backend(payload)


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
