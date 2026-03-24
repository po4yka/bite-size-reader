from __future__ import annotations

from pathlib import Path

from tests.architecture._import_rules import collect_forbidden_imports


def test_api_router_layer_avoids_direct_persistence_imports() -> None:
    """Routers must stay transport-only and import persistence via services/dependencies."""
    router_root = Path(__file__).resolve().parents[2] / "app" / "api" / "routers"
    violations = collect_forbidden_imports(
        router_root,
        forbidden_prefixes=(
            "app.db.models",
            "app.infrastructure.persistence.sqlite.repositories",
        ),
    )

    assert violations == []
