from __future__ import annotations

from pathlib import Path

from tests.architecture._import_rules import collect_forbidden_imports


def test_domain_layer_has_no_outer_layer_imports() -> None:
    domain_root = Path(__file__).resolve().parents[2] / "app" / "domain"
    violations = collect_forbidden_imports(
        domain_root,
        forbidden_prefixes=(
            "app.api",
            "app.db",
            "app.infrastructure",
            "app.adapters",
            "app.di",
        ),
    )

    assert violations == []
