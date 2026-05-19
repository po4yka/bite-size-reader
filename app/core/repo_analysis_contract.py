from __future__ import annotations

import json
from typing import Any, cast

from json_repair import repair_json

from app.core.repo_analysis_schema import RepoAnalysis

__all__ = [
    "parse_and_validate_repo_analysis",
    "repair_repo_analysis",
    "validate_repo_analysis",
]


def validate_repo_analysis(payload: dict[str, Any]) -> RepoAnalysis:
    """Strict validation. Raises pydantic.ValidationError on bad input."""
    return RepoAnalysis.model_validate(payload)


def repair_repo_analysis(raw: str) -> dict[str, Any]:
    """Use json_repair to recover from common LLM JSON errors. Returns dict (not validated)."""
    repaired = repair_json(raw, return_objects=True)
    if isinstance(repaired, dict):
        return repaired
    # repair_json may return a non-dict for severely malformed input
    if isinstance(repaired, str):
        return cast(dict[str, Any], json.loads(repaired))
    return {}


def parse_and_validate_repo_analysis(raw: str) -> RepoAnalysis:
    """Repair JSON then validate. Raises ValidationError on persistent issues."""
    payload = repair_repo_analysis(raw)
    return validate_repo_analysis(payload)
