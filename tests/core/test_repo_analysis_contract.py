from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.core.repo_analysis_contract import (
    parse_and_validate_repo_analysis,
    repair_repo_analysis,
    validate_repo_analysis,
)
from app.core.repo_analysis_schema import RepoAnalysis


def _valid_payload() -> dict:
    return {
        "purpose": "FastAPI is a modern async Python web framework.",
        "tech_stack": ["Python 3.11", "FastAPI", "Pydantic"],
        "architecture_summary": "Layered API with dependency injection and Pydantic-based validation.",
        "key_concepts": [
            {
                "term": "Dependency Injection",
                "explanation": "FastAPI resolves dependencies via callable signatures.",
            }
        ],
        "code_patterns": [],
        "use_cases": ["Build REST APIs"],
        "target_audience": "Python web developers",
        "maturity": "mature",
        "key_dependencies": ["starlette", "pydantic"],
        "hallucination_risk": "low",
        "confidence": 0.9,
    }


def test_valid_payload_validates() -> None:
    result = validate_repo_analysis(_valid_payload())
    assert isinstance(result, RepoAnalysis)
    assert result.confidence == 0.9
    assert result.maturity == "mature"


def test_missing_required_field_raises() -> None:
    payload = _valid_payload()
    del payload["purpose"]
    with pytest.raises(ValidationError):
        validate_repo_analysis(payload)


def test_oversized_tech_stack_rejected() -> None:
    payload = _valid_payload()
    payload["tech_stack"] = [f"tech{i}" for i in range(21)]
    with pytest.raises(ValidationError):
        validate_repo_analysis(payload)


def test_negative_confidence_rejected() -> None:
    payload = _valid_payload()
    payload["confidence"] = -0.1
    with pytest.raises(ValidationError):
        validate_repo_analysis(payload)


def test_repair_recovers_truncated_json() -> None:
    # Trailing comma — invalid JSON but recoverable
    raw = '{"purpose": "test",}'
    result = repair_repo_analysis(raw)
    assert isinstance(result, dict)
    assert result.get("purpose") == "test"


def test_parse_and_validate_round_trip() -> None:
    # Missing closing brace — json_repair should recover this
    payload = _valid_payload()
    raw = json.dumps(payload)[:-1]  # strip closing }
    result = parse_and_validate_repo_analysis(raw)
    assert isinstance(result, RepoAnalysis)
    assert result.confidence == 0.9
