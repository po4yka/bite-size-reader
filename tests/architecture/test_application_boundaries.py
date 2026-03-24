from __future__ import annotations

from pathlib import Path

from tests.architecture._import_rules import collect_forbidden_imports


def test_application_layer_has_no_outer_layer_imports() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app" / "application"
    violations = collect_forbidden_imports(
        app_root,
        forbidden_prefixes=(
            "app.api",
            "app.adapters",
            "app.db",
            "app.infrastructure",
            "app.di",
        ),
    )

    assert violations == []
