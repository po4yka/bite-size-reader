from __future__ import annotations

from pathlib import Path

from tests.architecture._import_rules import collect_forbidden_imports


def test_production_code_uses_adapter_models_namespace_instead_of_legacy_app_models() -> None:
    """Production imports should use the explicit adapter-model namespace."""
    app_root = Path(__file__).resolve().parents[2] / "app"
    violations = collect_forbidden_imports(
        app_root,
        forbidden_prefixes=("app.models",),
        ignored_path_prefixes=("app/models/",),
    )

    assert violations == []


def test_adapter_models_namespace_does_not_depend_on_legacy_app_models() -> None:
    """Canonical adapter models should not import the deprecated namespace."""
    adapter_models_root = Path(__file__).resolve().parents[2] / "app" / "adapter_models"
    violations = collect_forbidden_imports(
        adapter_models_root,
        forbidden_prefixes=("app.models",),
    )

    assert violations == []
