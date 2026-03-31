from __future__ import annotations

from typing import Any

from app.core.summary_schema import SummaryModel


def get_summary_json_schema() -> dict[str, Any]:
    """Return a JSON Schema for the summary contract."""

    def enforce_no_additional_props(schema_obj: Any) -> Any:
        if isinstance(schema_obj, dict):
            if schema_obj.get("type") == "object":
                schema_obj.setdefault("additionalProperties", False)

            for key in ("properties", "$defs", "definitions"):
                if key in schema_obj and isinstance(schema_obj[key], dict):
                    for _, sub in list(schema_obj[key].items()):
                        enforce_no_additional_props(sub)
            for key in ("items",):
                if key in schema_obj:
                    enforce_no_additional_props(schema_obj[key])
            for key in ("oneOf", "anyOf", "allOf"):
                if key in schema_obj and isinstance(schema_obj[key], list):
                    for sub in schema_obj[key]:
                        enforce_no_additional_props(sub)
        elif isinstance(schema_obj, list):
            for sub in schema_obj:
                enforce_no_additional_props(sub)
        return schema_obj

    def enforce_required_all(schema_obj: Any) -> Any:
        if isinstance(schema_obj, dict):
            if schema_obj.get("type") == "object" and isinstance(
                schema_obj.get("properties"), dict
            ):
                prop_keys = list(schema_obj["properties"].keys())
                schema_obj["required"] = prop_keys

                for _, sub in list(schema_obj["properties"].items()):
                    enforce_required_all(sub)

            for key in ("items",):
                if key in schema_obj:
                    enforce_required_all(schema_obj[key])
            for key in ("oneOf", "anyOf", "allOf"):
                if key in schema_obj and isinstance(schema_obj[key], list):
                    for sub in schema_obj[key]:
                        enforce_required_all(sub)
            for key in ("$defs", "definitions"):
                if key in schema_obj and isinstance(schema_obj[key], dict):
                    for _, sub in list(schema_obj[key].items()):
                        enforce_required_all(sub)
        elif isinstance(schema_obj, list):
            for sub in schema_obj:
                enforce_required_all(sub)
        return schema_obj

    def strip_unsupported_constraints(schema_obj: Any) -> Any:
        """Remove numeric constraints unsupported by some LLM providers.

        Anthropic (via OpenRouter) rejects minimum/maximum on number types.
        Strip these so the schema is universally accepted.
        """
        unsupported = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}
        if isinstance(schema_obj, dict):
            for key in unsupported:
                schema_obj.pop(key, None)
            for val in schema_obj.values():
                strip_unsupported_constraints(val)
        elif isinstance(schema_obj, list):
            for sub in schema_obj:
                strip_unsupported_constraints(sub)
        return schema_obj

    schema = SummaryModel.model_json_schema()

    if isinstance(schema, dict):
        schema.setdefault("type", "object")
        enforce_no_additional_props(schema)
        enforce_required_all(schema)
        strip_unsupported_constraints(schema)
        return schema

    return schema
