"""
Tests that ensure the OpenAPI spec (docs/openapi/mobile_api.yaml) stays in sync
with the FastAPI implementation.

Two test groups:
  1. Route coverage -- every FastAPI route has a matching path+method in the spec.
  2. Schema sync   -- Pydantic model fields/types match YAML spec schemas.

Run with:
    pytest tests/api/test_openapi_sync.py -v
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped,unused-ignore]

from app.api.exceptions import ErrorCode as ExceptionsErrorCode, ErrorType as ExceptionsErrorType

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi" / "mobile_api.yaml"

# HTTP methods we care about (skip OPTIONS which FastAPI auto-generates for CORS)
RELEVANT_METHODS = frozenset({"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD"})

# Routes that FastAPI registers automatically but are not user-facing API routes.
# These are excluded from the "must be documented" check.
IGNORED_APP_ROUTES = frozenset(
    {
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
        ("HEAD", "/openapi.json"),
        ("HEAD", "/docs"),
        ("HEAD", "/docs/oauth2-redirect"),
        ("HEAD", "/redoc"),
    }
)

# Routes that exist in the spec as aliases (e.g. /v1/articles is a mount of
# /v1/summaries router) and whose duplicate app routes should not be flagged.
# Map from spec path to the canonical app path it aliases.
SPEC_ALIASES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_spec() -> dict[str, Any]:
    with open(SPEC_PATH) as f:
        return yaml.safe_load(f)


def _extract_app_routes(app: Any) -> set[tuple[str, str]]:
    """Return {(METHOD, path)} from the running FastAPI app."""
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not (hasattr(route, "methods") and hasattr(route, "path")):
            continue
        for method in route.methods:
            method_upper = method.upper()
            if method_upper in RELEVANT_METHODS:
                routes.add((method_upper, route.path))
    return routes - IGNORED_APP_ROUTES


def _extract_spec_routes(spec: dict[str, Any]) -> set[tuple[str, str]]:
    """Return {(METHOD, path)} from the YAML spec."""
    routes: set[tuple[str, str]] = set()
    for path, methods in spec.get("paths", {}).items():
        for method in methods:
            method_upper = method.upper()
            if method_upper in RELEVANT_METHODS:
                routes.add((method_upper, path))
    return routes


def _normalize_type(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize an OpenAPI / Pydantic JSON-Schema property descriptor.

    Handles the differences between Pydantic v2 JSON Schema output and
    hand-written OpenAPI 3.1 YAML:

    * ``anyOf: [{type: X}, {type: null}]`` → base type + nullable flag
    * ``$ref`` paths are ignored (compared separately)
    * ``const`` vs single-value ``enum`` treated as equivalent
    """
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if non_null:
            result = dict(non_null[0])
            result["nullable"] = True
            return result
    return dict(schema)


def _resolve_all_schemas(spec: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of components/schemas with ``allOf`` references resolved.

    For schemas that use ``allOf`` (e.g. TelegramLinkCompleteRequest extends
    TelegramLoginRequest), we merge the referenced schema's properties and
    required fields into a single flat schema so tests can compare against
    the Pydantic model which uses Python inheritance.
    """
    raw_schemas = spec.get("components", {}).get("schemas", {})
    resolved: dict[str, Any] = {}

    for name, schema in raw_schemas.items():
        if "allOf" in schema:
            merged_props: dict[str, Any] = {}
            merged_required: list[str] = []
            for part in schema["allOf"]:
                if "$ref" in part:
                    ref_name = part["$ref"].rsplit("/", 1)[-1]
                    ref_schema = raw_schemas.get(ref_name, {})
                    merged_props.update(ref_schema.get("properties", {}))
                    merged_required.extend(ref_schema.get("required", []))
                else:
                    merged_props.update(part.get("properties", {}))
                    merged_required.extend(part.get("required", []))
            resolved[name] = {
                "type": "object",
                "properties": merged_props,
                "required": merged_required,
            }
        else:
            resolved[name] = schema

    return resolved


def _property_names(schema: dict[str, Any]) -> set[str]:
    """Extract property names from a JSON Schema / OpenAPI schema object."""
    return set(schema.get("properties", {}).keys())


def _required_fields(schema: dict[str, Any]) -> set[str]:
    """Extract required field names."""
    return set(schema.get("required", []))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return _load_spec()


@pytest.fixture(scope="module")
def spec_schemas(spec: dict[str, Any]) -> dict[str, Any]:
    return _resolve_all_schemas(spec)


@pytest.fixture
def app_instance(client):  # client triggers app init side-effects
    """Return the FastAPI app after it has been properly initialised via the
    ``client`` fixture (env vars, DB, module reload)."""
    from app.api.main import app

    return app


# ---------------------------------------------------------------------------
# 1. Route coverage
# ---------------------------------------------------------------------------


class TestRouteCoverage:
    """Every FastAPI route must have a matching entry in the YAML spec."""

    def test_all_routes_documented(self, app_instance: Any, spec: dict[str, Any]) -> None:
        app_routes = _extract_app_routes(app_instance)
        spec_routes = _extract_spec_routes(spec)

        # Normalise path params: FastAPI uses {summary_id}, YAML uses {summary_id} — same.
        undocumented = app_routes - spec_routes
        if undocumented:
            formatted = "\n".join(f"  {m} {p}" for m, p in sorted(undocumented))
            pytest.fail(
                f"The following app routes are NOT in the OpenAPI spec:\n{formatted}\n\n"
                "Add them to docs/openapi/mobile_api.yaml or to IGNORED_APP_ROUTES "
                "in this test if they should be excluded."
            )

    def test_no_orphan_spec_routes(self, app_instance: Any, spec: dict[str, Any]) -> None:
        """Warn (do not fail) if the spec has routes absent from the app."""
        app_routes = _extract_app_routes(app_instance)
        spec_routes = _extract_spec_routes(spec)

        orphans = spec_routes - app_routes
        if orphans:
            formatted = "\n".join(f"  {m} {p}" for m, p in sorted(orphans))
            warnings.warn(
                f"Spec routes with no matching app route:\n{formatted}\n"
                "These may be deprecated aliases or planned endpoints.",
                stacklevel=1,
            )


# ---------------------------------------------------------------------------
# 2. Schema sync
# ---------------------------------------------------------------------------


class TestSchemaSync:
    """Pydantic model property names must match YAML spec schema properties."""

    def _get_registry(self) -> dict[str, type]:
        from tests.api.openapi_schema_registry import SCHEMA_REGISTRY

        return SCHEMA_REGISTRY

    def _pydantic_json_schema(self, model_cls: type) -> dict[str, Any]:
        return model_cls.model_json_schema()  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "schema_name",
        sorted(
            # Lazy import so collection is deferred until parametrize time
            __import__(
                "tests.api.openapi_schema_registry", fromlist=["SCHEMA_REGISTRY"]
            ).SCHEMA_REGISTRY.keys()
        ),
    )
    def test_property_names_match(
        self,
        schema_name: str,
        spec_schemas: dict[str, Any],
    ) -> None:
        registry = self._get_registry()
        model_cls = registry[schema_name]

        if schema_name not in spec_schemas:
            pytest.skip(f"Schema '{schema_name}' not found in YAML spec (may be inline)")

        pydantic_schema = self._pydantic_json_schema(model_cls)
        yaml_schema = spec_schemas[schema_name]

        pydantic_props = _property_names(pydantic_schema)
        yaml_props = _property_names(yaml_schema)

        # Pydantic may use the field's alias for serialisation; the YAML spec
        # typically uses the alias (camelCase / wire name).  We need to build
        # a mapping from Python attr name -> alias so we can compare correctly.
        alias_map = _build_alias_map(model_cls)
        pydantic_wire_names = {alias_map.get(p, p) for p in pydantic_props}

        missing_in_spec = pydantic_wire_names - yaml_props
        missing_in_code = yaml_props - pydantic_wire_names

        errors: list[str] = []
        if missing_in_spec:
            errors.append(f"In code but NOT in spec: {sorted(missing_in_spec)}")
        if missing_in_code:
            errors.append(f"In spec but NOT in code: {sorted(missing_in_code)}")

        if errors:
            pytest.fail(
                f"Property mismatch for schema '{schema_name}':\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    @pytest.mark.parametrize(
        "schema_name",
        sorted(
            __import__(
                "tests.api.openapi_schema_registry", fromlist=["SCHEMA_REGISTRY"]
            ).SCHEMA_REGISTRY.keys()
        ),
    )
    def test_required_fields_match(
        self,
        schema_name: str,
        spec_schemas: dict[str, Any],
    ) -> None:
        registry = self._get_registry()
        model_cls = registry[schema_name]

        if schema_name not in spec_schemas:
            pytest.skip(f"Schema '{schema_name}' not found in YAML spec (may be inline)")

        pydantic_schema = self._pydantic_json_schema(model_cls)
        yaml_schema = spec_schemas[schema_name]

        alias_map = _build_alias_map(model_cls)

        pydantic_required = {alias_map.get(f, f) for f in _required_fields(pydantic_schema)}
        yaml_required = _required_fields(yaml_schema)

        if pydantic_required != yaml_required:
            only_code = pydantic_required - yaml_required
            only_spec = yaml_required - pydantic_required
            parts: list[str] = []
            if only_code:
                parts.append(f"Required in code only: {sorted(only_code)}")
            if only_spec:
                parts.append(f"Required in spec only: {sorted(only_spec)}")
            pytest.fail(
                f"Required-field mismatch for schema '{schema_name}':\n"
                + "\n".join(f"  - {p}" for p in parts)
            )


# ---------------------------------------------------------------------------
# 3. Error enum sync
# ---------------------------------------------------------------------------


class TestErrorEnumSync:
    """ErrorCode and ErrorType enums in exceptions.py must match YAML spec."""

    def test_error_codes_match(self, spec_schemas: dict[str, Any]) -> None:
        error_obj = spec_schemas.get("ErrorObject")
        assert error_obj is not None, "ErrorObject schema missing from YAML spec"

        spec_codes = set(error_obj["properties"]["code"]["enum"])
        code_values = {e.value for e in ExceptionsErrorCode}

        missing_in_spec = code_values - spec_codes
        missing_in_code = spec_codes - code_values

        errors: list[str] = []
        if missing_in_spec:
            errors.append(f"In code but NOT in spec: {sorted(missing_in_spec)}")
        if missing_in_code:
            errors.append(f"In spec but NOT in code: {sorted(missing_in_code)}")

        if errors:
            pytest.fail("ErrorCode enum mismatch:\n" + "\n".join(f"  - {e}" for e in errors))

    def test_error_types_match(self, spec_schemas: dict[str, Any]) -> None:
        error_obj = spec_schemas.get("ErrorObject")
        assert error_obj is not None, "ErrorObject schema missing from YAML spec"

        spec_types = set(error_obj["properties"]["errorType"]["enum"])
        type_values = {e.value for e in ExceptionsErrorType}

        missing_in_spec = type_values - spec_types
        missing_in_code = spec_types - type_values

        errors: list[str] = []
        if missing_in_spec:
            errors.append(f"In code but NOT in spec: {sorted(missing_in_spec)}")
        if missing_in_code:
            errors.append(f"In spec but NOT in code: {sorted(missing_in_code)}")

        if errors:
            pytest.fail("ErrorType enum mismatch:\n" + "\n".join(f"  - {e}" for e in errors))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_alias_map(model_cls: type) -> dict[str, str]:
    """Return {python_field_name: wire_name} for a Pydantic model.

    The wire name is determined by checking (in order):
    1. serialization_alias (used for output / wire format)
    2. validation_alias (used for input parsing)
    3. alias (general alias)
    4. Python attribute name (fallback)
    """
    mapping: dict[str, str] = {}
    for field_name, field_info in model_cls.model_fields.items():  # type: ignore[attr-defined]
        wire = field_name
        if field_info.serialization_alias:
            wire = field_info.serialization_alias
        elif field_info.validation_alias and isinstance(field_info.validation_alias, str):
            wire = field_info.validation_alias
        elif field_info.alias:
            wire = field_info.alias
        mapping[field_name] = wire
    return mapping
