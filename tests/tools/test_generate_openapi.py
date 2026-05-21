from __future__ import annotations

import json

import yaml  # type: ignore[import-untyped]

from app.api.models.responses.common import API_CONTRACT_VERSION
from tools.scripts.generate_openapi import (
    JSON_PATH,
    YAML_PATH,
    _render_json,
    _render_yaml,
    generate_spec,
)


def test_generated_openapi_version_matches_contract_version() -> None:
    spec = generate_spec()

    assert spec["info"]["version"] == API_CONTRACT_VERSION


def test_committed_openapi_docs_match_generator() -> None:
    spec = generate_spec()

    assert YAML_PATH.read_text() == _render_yaml(spec)
    assert JSON_PATH.read_text() == _render_json(spec)


def test_committed_openapi_yaml_and_json_are_equivalent() -> None:
    yaml_spec = yaml.safe_load(YAML_PATH.read_text())
    json_spec = json.loads(JSON_PATH.read_text())

    assert yaml_spec == json_spec
