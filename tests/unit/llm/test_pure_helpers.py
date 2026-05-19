"""Unit tests for pure-logic helpers in the LLM adapter layer.

Covers ``schema_simplifier``, ``exceptions``, and the synchronous parts of
``client_validation`` and ``error_handler``. Strictly offline.
"""

from __future__ import annotations

import pytest

from app.adapters.openrouter.client_validation import (
    get_error_message,
    validate_init_params,
)
from app.adapters.openrouter.exceptions import (
    ConfigurationError,
    OpenRouterError,
    ValidationError,
)
from app.adapters.openrouter.schema_simplifier import (
    SchemaSimplificationExhausted,
    simplification_steps,
    simplify_schema,
)

pytestmark = pytest.mark.no_network


# ---------------------------------------------------------------------------
# schema_simplifier
# ---------------------------------------------------------------------------


def _ref_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["a"],
        "properties": {
            "a": {
                "oneOf": [
                    {"type": "string", "additionalProperties": False},
                ]
            },
            "b": {"$ref": "#/$defs/B"},
        },
        "$defs": {"B": {"type": "integer"}},
    }


def test_simplification_steps_returns_expected_count() -> None:
    assert simplification_steps() == 5


def test_simplify_schema_step_zero_returns_defensive_copy() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 0)
    assert out == schema
    out["new"] = "key"
    assert "new" not in schema  # original untouched


def test_simplify_schema_step_one_strips_additional_properties_false() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 1)
    assert "additionalProperties" not in out
    assert "additionalProperties" not in out["properties"]["a"]["oneOf"][0]


def test_simplify_schema_step_two_unwraps_single_branch_oneof() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 2)
    # The single-branch oneOf in properties.a should be unwrapped to its child.
    assert "oneOf" not in out["properties"]["a"]


def test_simplify_schema_step_three_inlines_refs_and_drops_defs() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 3)
    assert "$defs" not in out
    assert out["properties"]["b"] == {"type": "integer"}


def test_simplify_schema_step_four_removes_required_arrays() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 4)
    assert "required" not in out


def test_simplify_schema_step_five_reduces_leaves_to_type_only() -> None:
    schema = _ref_schema()
    out = simplify_schema(schema, 5)
    # Every leaf should keep only a "type" hint.
    b = out["properties"]["b"]
    assert b == {"type": "integer"}


def test_simplify_schema_negative_step_raises_value_error() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        simplify_schema(_ref_schema(), -1)


def test_simplify_schema_step_above_max_raises_exhausted() -> None:
    with pytest.raises(SchemaSimplificationExhausted):
        simplify_schema(_ref_schema(), simplification_steps() + 1)


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------


def test_openrouter_error_records_metadata_into_context() -> None:
    exc = OpenRouterError(
        "boom",
        model="m1",
        attempt=2,
        request_id=7,
        context={"foo": "bar"},
    )
    assert exc.model == "m1"
    assert exc.attempt == 2
    assert exc.request_id == 7
    assert exc.context == {"foo": "bar"}
    assert str(exc) == "boom"


def test_configuration_error_tags_context_with_error_type() -> None:
    exc = ConfigurationError("nope", model=None)
    assert exc.context["error_type"] == "configuration"


def test_validation_error_tags_context_with_error_type() -> None:
    exc = ValidationError("bad input")
    assert exc.context["error_type"] == "validation"


def test_configuration_error_is_openrouter_error_subclass() -> None:
    assert issubclass(ConfigurationError, OpenRouterError)
    assert issubclass(ValidationError, OpenRouterError)


# ---------------------------------------------------------------------------
# client_validation.get_error_message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected_base"),
    [
        (400, "Invalid or missing request parameters"),
        (401, "Authentication failed"),
        (402, "Insufficient account balance"),
        (404, "Requested resource not found"),
        (429, "Rate limit exceeded"),
        (500, "Internal server error"),
    ],
)
def test_get_error_message_known_statuses(status_code: int, expected_base: str) -> None:
    assert get_error_message(status_code, None) == expected_base


def test_get_error_message_5xx_above_500_uses_generic_template() -> None:
    assert "HTTP 502" in get_error_message(502, None)
    assert "HTTP 503" in get_error_message(503, None)


def test_get_error_message_appends_api_message_from_dict() -> None:
    payload = {"error": {"message": "Quota exceeded"}}
    out = get_error_message(429, payload)
    assert out == "Rate limit exceeded: Quota exceeded"


def test_get_error_message_appends_api_message_from_string_error() -> None:
    out = get_error_message(400, {"error": "invalid_field"})
    assert out == "Invalid or missing request parameters: invalid_field"


def test_get_error_message_handles_missing_error_block() -> None:
    out = get_error_message(401, {})
    assert out == "Authentication failed"


def test_get_error_message_returns_generic_for_unknown_status() -> None:
    assert "HTTP 418" in get_error_message(418, None)


# ---------------------------------------------------------------------------
# client_validation.validate_init_params
# ---------------------------------------------------------------------------


_VALID_KWARGS = {
    "api_key": "sk-or-v1-test-key-1234567890",
    "model": "qwen/qwen3-max",
    "fallback_models": (),
    "http_referer": None,
    "x_title": None,
    "timeout_sec": 30,
    "max_retries": 3,
    "backoff_base": 1.5,
    "structured_output_mode": "json_schema",
    "max_response_size_mb": 50,
}


def test_validate_init_params_accepts_well_formed_kwargs() -> None:
    # Should not raise.
    validate_init_params(**_VALID_KWARGS)


def test_validate_init_params_rejects_missing_api_key() -> None:
    bad = {**_VALID_KWARGS, "api_key": ""}
    with pytest.raises(ConfigurationError, match="API key"):
        validate_init_params(**bad)


def test_validate_init_params_rejects_short_api_key() -> None:
    bad = {**_VALID_KWARGS, "api_key": "short"}
    with pytest.raises(ConfigurationError, match="API key"):
        validate_init_params(**bad)


def test_validate_init_params_rejects_empty_model() -> None:
    bad = {**_VALID_KWARGS, "model": ""}
    with pytest.raises(ConfigurationError, match="Model"):
        validate_init_params(**bad)


def test_validate_init_params_rejects_non_string_model() -> None:
    bad = {**_VALID_KWARGS, "model": 12345}
    with pytest.raises(ConfigurationError):
        validate_init_params(**bad)


def test_validate_init_params_rejects_non_string_api_key() -> None:
    bad = {**_VALID_KWARGS, "api_key": 12345}
    with pytest.raises(ConfigurationError):
        validate_init_params(**bad)
