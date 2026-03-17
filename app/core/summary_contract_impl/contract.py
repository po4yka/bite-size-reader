from __future__ import annotations

import logging

from app.core.summary_contract_impl.common import SummaryJSON
from app.core.summary_contract_impl.field_names import normalize_field_names
from app.core.summary_contract_impl.rag_fields import shape_rag_fields
from app.core.summary_contract_impl.schema_helpers import get_summary_json_schema
from app.core.summary_contract_impl.summary_shaper import (
    backfill_summary_fields,
    populate_keywords_if_missing,
    shape_base_summary_fields,
    shape_extended_summary_fields,
    validate_summary_payload_input,
)
from app.core.summary_contract_impl.text_shaping import extract_keywords_tfidf, normalize_whitespace
from app.core.summary_schema import SummaryModel
from app.core.summary_text_utils import cap_text
from app.types.summary_types import (
    Entities,
    KeyStat,
    Metadata,
    Readability,
    SemanticChunk,
    SummaryDict,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Entities",
    "KeyStat",
    "Metadata",
    "Readability",
    "SemanticChunk",
    "SummaryDict",
    "SummaryJSON",
    "cap_text",
    "extract_keywords_tfidf",
    "get_summary_json_schema",
    "normalize_whitespace",
    "validate_and_shape_summary",
]


def validate_and_shape_summary(payload: SummaryJSON) -> SummaryJSON:
    """Validate and shape a model-produced summary to the canonical contract."""
    validate_summary_payload_input(payload)
    shaped_payload: SummaryJSON = normalize_field_names(payload)

    backfill_summary_fields(shaped_payload, payload)
    readability_source = shape_base_summary_fields(shaped_payload)
    populate_keywords_if_missing(shaped_payload, readability_source)
    shape_extended_summary_fields(shaped_payload)
    shape_rag_fields(shaped_payload)

    try:
        model = SummaryModel(**shaped_payload)
        return model.model_dump()
    except Exception as exc:
        logger.warning("pydantic_validation_fallback", extra={"error": str(exc)})
        return shaped_payload
