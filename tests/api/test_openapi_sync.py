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
        # SPA frontend routes -- not REST API endpoints
        ("GET", "/web"),
        ("GET", "/web/{path:path}"),
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
# 4. Envelope / wire-shape conventions
# ---------------------------------------------------------------------------


class TestWireShapeConventions:
    """Critical response envelopes should match runtime wire casing/shape."""

    def test_pagination_uses_has_more_alias(self, spec: dict[str, Any]) -> None:
        pagination = spec["components"]["schemas"]["Pagination"]
        required = set(pagination.get("required", []))
        properties = set(pagination.get("properties", {}).keys())

        assert "hasMore" in required
        assert "hasMore" in properties
        assert "has_more" not in properties

    def test_submit_request_data_is_nested_request_object(self, spec: dict[str, Any]) -> None:
        submit_data = spec["components"]["schemas"]["SubmitRequestData"]
        assert submit_data.get("required") == ["request"]
        request_prop = submit_data["properties"]["request"]
        assert request_prop["$ref"] == "#/components/schemas/SubmitRequestResponse"

    def test_request_status_schema_uses_camel_case_wire_keys(self, spec: dict[str, Any]) -> None:
        status_data = spec["components"]["schemas"]["RequestStatusData"]
        required = set(status_data.get("required", []))
        props = set(status_data.get("properties", {}).keys())

        assert {"requestId", "canRetry", "updatedAt"}.issubset(required)
        assert {"requestId", "canRetry", "updatedAt"}.issubset(props)
        assert "request_id" not in props
        assert "can_retry" not in props
        assert "updated_at" not in props

    def test_success_response_requires_data_envelope(self, spec: dict[str, Any]) -> None:
        success = spec["components"]["schemas"]["SuccessResponse"]
        assert "allOf" in success
        has_base_success_ref = any(
            isinstance(part, dict)
            and part.get("$ref") == "#/components/schemas/BaseSuccessResponse"
            for part in success["allOf"]
        )
        assert has_base_success_ref, "SuccessResponse must include BaseSuccessResponse"

    def test_response_status_code_keys_are_strings(self, spec: dict[str, Any]) -> None:
        """YAML response status keys must be quoted/string-typed for tool compatibility."""
        errors: list[str] = []
        for path, methods in spec.get("paths", {}).items():
            for method, operation in methods.items():
                method_upper = method.upper()
                if method_upper not in RELEVANT_METHODS:
                    continue
                responses = operation.get("responses", {})
                for key in responses:
                    if not isinstance(key, str):
                        errors.append(f"{method_upper} {path} has non-string response key: {key!r}")
        if errors:
            pytest.fail("Non-string response status keys found:\n" + "\n".join(errors))

    def test_secured_operations_document_4xx_and_5xx(self, spec: dict[str, Any]) -> None:
        """Every HTTPBearer-protected operation should document both client/server errors."""
        failures: list[str] = []

        for path, methods in spec.get("paths", {}).items():
            for method, operation in methods.items():
                method_upper = method.upper()
                if method_upper not in RELEVANT_METHODS:
                    continue

                security = operation.get("security") or []
                uses_http_bearer = any(
                    isinstance(sec_req, dict) and "HTTPBearer" in sec_req for sec_req in security
                )
                if not uses_http_bearer:
                    continue

                responses = operation.get("responses", {})
                has_4xx = any(str(code).startswith("4") for code in responses)
                has_5xx = any(str(code).startswith("5") for code in responses)
                if not has_4xx or not has_5xx:
                    failures.append(f"{method_upper} {path} (has_4xx={has_4xx}, has_5xx={has_5xx})")

        if failures:
            pytest.fail(
                "Secured operations missing documented 4xx/5xx responses:\n" + "\n".join(failures)
            )

    def test_user_schema_uses_camel_case_wire_keys(self, spec: dict[str, Any]) -> None:
        user = spec["components"]["schemas"]["User"]
        required = set(user.get("required", []))
        props = set(user.get("properties", {}).keys())

        expected = {"userId", "username", "clientId", "isOwner", "createdAt"}
        assert expected.issubset(required)
        assert expected.issubset(props)
        assert "id" not in props
        assert "is_owner" not in props
        assert "client_id" not in props
        assert "created_at" not in props

    def test_user_stats_schema_uses_camel_case_wire_keys(self, spec: dict[str, Any]) -> None:
        stats = spec["components"]["schemas"]["UserStats"]
        required = set(stats.get("required", []))
        props = set(stats.get("properties", {}).keys())

        expected = {
            "totalSummaries",
            "unreadCount",
            "readCount",
            "totalReadingTimeMin",
            "averageReadingTimeMin",
            "favoriteTopics",
            "favoriteDomains",
            "languageDistribution",
        }
        assert expected.issubset(required)
        assert expected.issubset(props)
        assert "total_summaries" not in props
        assert "unread_count" not in props
        assert "favorite_topics" not in props
        assert "favorite_domains" not in props

    def test_summary_list_schema_uses_runtime_wire_shape(self, spec: dict[str, Any]) -> None:
        paginated = spec["components"]["schemas"]["PaginatedSummariesData"]
        required = set(paginated.get("required", []))
        props = set(paginated.get("properties", {}).keys())
        assert "summaries" in required
        assert "summaries" in props
        assert "items" not in props

        summary_item = spec["components"]["schemas"]["SummaryListItem"]
        item_required = set(summary_item.get("required", []))
        item_props = set(summary_item.get("properties", {}).keys())
        expected_item = {
            "requestId",
            "summary250",
            "readingTimeMin",
            "topicTags",
            "isRead",
            "createdAt",
            "hallucinationRisk",
        }
        assert expected_item.issubset(item_required)
        assert expected_item.issubset(item_props)
        assert "request_id" not in item_props
        assert "summary_250" not in item_props
        assert "reading_time_min" not in item_props

    def test_summary_content_schema_uses_camel_case_wire_keys(self, spec: dict[str, Any]) -> None:
        content = spec["components"]["schemas"]["SummaryContent"]
        required = set(content.get("required", []))
        props = set(content.get("properties", {}).keys())
        expected = {"summaryId", "contentType", "retrievedAt"}
        assert expected.issubset(required)
        assert expected.issubset(props)
        assert "summary_id" not in props
        assert "content_type" not in props
        assert "retrieved_at" not in props

    def test_collection_schema_uses_camel_case_wire_keys(self, spec: dict[str, Any]) -> None:
        collection = spec["components"]["schemas"]["Collection"]
        required = set(collection.get("required", []))
        props = set(collection.get("properties", {}).keys())
        expected = {"createdAt", "updatedAt", "serverVersion", "isShared"}
        assert expected.issubset(required)
        assert expected.issubset(props)
        assert "created_at" not in props
        assert "updated_at" not in props
        assert "is_shared" not in props

        item = spec["components"]["schemas"]["CollectionItem"]
        item_required = set(item.get("required", []))
        item_props = set(item.get("properties", {}).keys())
        assert {"collectionId", "summaryId", "createdAt"}.issubset(item_required)
        assert {"collectionId", "summaryId", "createdAt"}.issubset(item_props)
        assert "collection_id" not in item_props
        assert "summary_id" not in item_props
        assert "created_at" not in item_props


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
