from __future__ import annotations

from pathlib import Path

from tests.architecture._import_rules import collect_forbidden_imports

LEGACY_PERSISTENCE_ROUTER_ALLOWLIST = (
    "routers/admin.py",
    "routers/auth/",
    "routers/backups.py",
    "routers/custom_digests.py",
    "routers/import_export.py",
    "routers/notifications.py",
    "routers/quick_save.py",
    "routers/rules.py",
    "routers/search.py",
    "routers/tags.py",
    "routers/tts.py",
    "routers/user.py",
    "routers/webhooks.py",
)


def test_api_router_layer_avoids_direct_persistence_imports_outside_legacy_allowlist() -> None:
    """Legacy router DB access is debt-shrink only; new routers must stay transport-only."""
    router_root = Path(__file__).resolve().parents[2] / "app" / "api" / "routers"
    violations = collect_forbidden_imports(
        router_root,
        forbidden_prefixes=(
            "app.db.models",
            "app.infrastructure.persistence.sqlite.repositories",
        ),
        ignored_path_prefixes=LEGACY_PERSISTENCE_ROUTER_ALLOWLIST,
    )

    assert violations == []
