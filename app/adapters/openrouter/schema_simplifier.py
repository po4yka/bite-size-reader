"""Progressive JSON Schema simplifier for OpenRouter structured-output retry.

When a provider returns a 400 implying that a specific JSON Schema
construct is unsupported (rather than rejecting structured output
wholesale), this module exposes an ordered sequence of transformations
that strip one strict-mode feature at a time, preserving as much
field-level validation as possible before the existing binary
``json_schema -> json_object -> off`` downgrade takes over.

Step order:
  1. Strip ``additionalProperties: false`` everywhere (most common offender).
  2. Unwrap single-branch ``oneOf``/``anyOf``.
  3. Inline ``$ref`` to ``$defs`` and drop ``$defs``.
  4. Remove all ``required`` arrays.
  5. Reduce every leaf to a bare ``{"type": <primitive>}`` hint.

Step 0 returns a defensive copy of the input. Asking for a step beyond
the configured count raises ``SchemaSimplificationExhausted`` so the
caller knows to fall back to the binary downgrade.
"""

from __future__ import annotations

import copy
from typing import Any

_TOTAL_STEPS = 5


class SchemaSimplificationExhausted(RuntimeError):
    """Raised when the caller asks for a simplification step beyond the max."""


def simplification_steps() -> int:
    """Return the number of progressive simplification steps available."""
    return _TOTAL_STEPS


def simplify_schema(schema: dict[str, Any], step: int) -> dict[str, Any]:
    """Return a copy of *schema* with simplifications 1..step applied.

    ``step == 0`` returns a defensive copy unchanged. ``step`` larger
    than :func:`simplification_steps` raises
    :class:`SchemaSimplificationExhausted`.
    """
    if step < 0:
        raise ValueError("step must be >= 0")
    if step > _TOTAL_STEPS:
        raise SchemaSimplificationExhausted(
            f"requested step {step} exceeds max {_TOTAL_STEPS}"
        )

    out = copy.deepcopy(schema)
    if step >= 1:
        out = _strip_additional_properties_false(out)
    if step >= 2:
        out = _unwrap_single_branch_alternation(out)
    if step >= 3:
        out = _flatten_defs(out)
    if step >= 4:
        out = _strip_required(out)
    if step >= 5:
        out = _reduce_to_bare_types(out)
    return out


def _walk(node: Any, fn: Any) -> Any:
    """Apply *fn* to every dict node, recursing into dict values and lists."""
    if isinstance(node, dict):
        node = fn(node)
        for key, value in list(node.items()):
            node[key] = _walk(value, fn)
        return node
    if isinstance(node, list):
        return [_walk(item, fn) for item in node]
    return node


def _strip_additional_properties_false(schema: dict[str, Any]) -> dict[str, Any]:
    def fn(node: dict[str, Any]) -> dict[str, Any]:
        if node.get("additionalProperties") is False:
            node.pop("additionalProperties", None)
        return node

    return _walk(schema, fn)


def _unwrap_single_branch_alternation(schema: dict[str, Any]) -> dict[str, Any]:
    def fn(node: dict[str, Any]) -> dict[str, Any]:
        for key in ("oneOf", "anyOf"):
            branches = node.get(key)
            if isinstance(branches, list) and len(branches) == 1 and isinstance(
                branches[0], dict
            ):
                inlined = copy.deepcopy(branches[0])
                node.pop(key)
                # Merge inlined keys without overwriting explicit siblings.
                for k, v in inlined.items():
                    node.setdefault(k, v)
        return node

    return _walk(schema, fn)


def _flatten_defs(schema: dict[str, Any]) -> dict[str, Any]:
    defs = schema.get("$defs") or {}
    if not defs:
        return schema

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target_name = ref.removeprefix("#/$defs/")
                target = defs.get(target_name)
                if isinstance(target, dict):
                    return resolve(copy.deepcopy(target))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    resolved = resolve(schema)
    if isinstance(resolved, dict):
        resolved.pop("$defs", None)
    return resolved


def _strip_required(schema: dict[str, Any]) -> dict[str, Any]:
    def fn(node: dict[str, Any]) -> dict[str, Any]:
        node.pop("required", None)
        return node

    return _walk(schema, fn)


_LEAF_TYPE_KEYWORDS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "enum",
    "const",
    "minItems",
    "maxItems",
    "uniqueItems",
}


def _reduce_to_bare_types(schema: dict[str, Any]) -> dict[str, Any]:
    def fn(node: dict[str, Any]) -> dict[str, Any]:
        node_type = node.get("type")
        if isinstance(node_type, str) and node_type not in ("object", "array"):
            for key in list(node.keys()):
                if key in _LEAF_TYPE_KEYWORDS:
                    node.pop(key)
        return node

    return _walk(schema, fn)
