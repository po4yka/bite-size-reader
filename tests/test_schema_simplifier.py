"""Tests for the progressive JSON schema simplifier.

The simplifier is used by the OpenRouter retry loop when a provider returns
a 400 that implies a structured-output construct rejection. Each successive
step strips one feature, preserving as much field-level validation as
possible before the existing binary downgrade (json_schema -> json_object
-> off) takes over.
"""

from __future__ import annotations

import copy

import pytest

from app.adapters.openrouter.schema_simplifier import (
    SchemaSimplificationExhausted,
    simplification_steps,
    simplify_schema,
)


@pytest.fixture
def strict_summary_schema() -> dict:
    """A representative strict schema using all problematic constructs."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary_250", "tldr"],
        "properties": {
            "summary_250": {"type": "string", "minLength": 1, "maxLength": 250},
            "tldr": {"type": "string"},
            "source": {
                "oneOf": [
                    {"type": "object", "properties": {"url": {"type": "string"}}},
                    {"type": "null"},
                ],
            },
            "tags": {
                "type": "array",
                "items": {"$ref": "#/$defs/Tag"},
            },
        },
        "$defs": {
            "Tag": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"name": {"type": "string"}},
            },
        },
    }


class TestRemoveAdditionalPropertiesFalse:
    def test_strips_additional_properties_false_at_root(self) -> None:
        schema = {"type": "object", "additionalProperties": False, "properties": {}}
        out = simplify_schema(schema, step=1)
        assert "additionalProperties" not in out

    def test_strips_additional_properties_false_nested(
        self, strict_summary_schema: dict
    ) -> None:
        out = simplify_schema(strict_summary_schema, step=1)
        # Both root and the nested $defs/Tag had additionalProperties: false
        assert "additionalProperties" not in out
        assert "additionalProperties" not in out["$defs"]["Tag"]

    def test_preserves_additional_properties_when_true_or_schema(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": {"type": "string"},
        }
        out = simplify_schema(schema, step=1)
        assert out["additionalProperties"] == {"type": "string"}

    def test_input_not_mutated(self, strict_summary_schema: dict) -> None:
        snapshot = copy.deepcopy(strict_summary_schema)
        simplify_schema(strict_summary_schema, step=1)
        assert strict_summary_schema == snapshot


class TestUnwrapSingleBranchAlternation:
    def test_unwraps_single_branch_oneof(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "value": {"oneOf": [{"type": "string"}]},
            },
        }
        out = simplify_schema(schema, step=2)
        assert out["properties"]["value"] == {"type": "string"}

    def test_unwraps_single_branch_anyof(self) -> None:
        schema = {"properties": {"v": {"anyOf": [{"type": "integer"}]}}}
        out = simplify_schema(schema, step=2)
        assert out["properties"]["v"] == {"type": "integer"}

    def test_keeps_multi_branch_oneof(self) -> None:
        schema = {
            "properties": {
                "v": {"oneOf": [{"type": "string"}, {"type": "null"}]},
            },
        }
        out = simplify_schema(schema, step=2)
        assert "oneOf" in out["properties"]["v"]


class TestFlattenDefs:
    def test_inlines_ref_targets_and_removes_defs(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "tag": {"$ref": "#/$defs/Tag"},
            },
            "$defs": {
                "Tag": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        }
        out = simplify_schema(schema, step=3)
        assert "$defs" not in out
        assert out["properties"]["tag"] == {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

    def test_no_defs_is_noop(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        out = simplify_schema(schema, step=3)
        assert out == schema


class TestRemoveRequired:
    def test_drops_required_arrays(self) -> None:
        schema = {
            "type": "object",
            "required": ["a"],
            "properties": {"a": {"type": "string"}},
        }
        out = simplify_schema(schema, step=4)
        assert "required" not in out


class TestBareTypeHints:
    def test_strips_all_constraints_leaving_types(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "summary_250": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 250,
                    "pattern": "^.+$",
                },
                "count": {"type": "integer", "minimum": 0, "maximum": 100},
            },
        }
        out = simplify_schema(schema, step=5)
        assert out["properties"]["summary_250"] == {"type": "string"}
        assert out["properties"]["count"] == {"type": "integer"}


class TestStepCount:
    def test_simplification_steps_returns_five(self) -> None:
        # 5 ordered steps as documented in the task spec.
        assert simplification_steps() == 5

    def test_step_zero_returns_original_copy(
        self, strict_summary_schema: dict
    ) -> None:
        out = simplify_schema(strict_summary_schema, step=0)
        assert out == strict_summary_schema
        # Defensive copy
        assert out is not strict_summary_schema

    def test_step_beyond_max_raises(self, strict_summary_schema: dict) -> None:
        with pytest.raises(SchemaSimplificationExhausted):
            simplify_schema(strict_summary_schema, step=6)

    def test_each_step_is_cumulative(self, strict_summary_schema: dict) -> None:
        # Step N applies steps 1..N in order.
        step1 = simplify_schema(strict_summary_schema, step=1)
        assert "additionalProperties" not in step1
        # Step 5 must also have additionalProperties stripped.
        step5 = simplify_schema(strict_summary_schema, step=5)
        assert "additionalProperties" not in step5
        # Step 5 must additionally have no required arrays and bare types.
        assert "required" not in step5
