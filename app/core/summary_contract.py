from __future__ import annotations

from typing import Any

from app.core.summary_contract_impl.contract import (
    _cap_text,
    _extract_keywords_tfidf,
    _normalize_whitespace,
    get_summary_json_schema,
    validate_and_shape_summary as _validate_and_shape_summary_python,
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
    - ``SUMMARY_CONTRACT_BACKEND=rust`` (default): prefer Rust with Python fallback on failures
    - ``SUMMARY_CONTRACT_BACKEND=auto``: use Rust when binary is available, else Python fallback
    - ``SUMMARY_CONTRACT_BACKEND=python``: force Python implementation
    """

    return validate_with_backend(payload, python_fallback=_validate_and_shape_summary_python)


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
