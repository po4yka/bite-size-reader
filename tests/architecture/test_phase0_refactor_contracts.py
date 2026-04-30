from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_cli_migrations_are_the_only_versioned_migration_modules() -> None:
    db_migrations_dir = ROOT / "app/db/migrations"
    if not db_migrations_dir.exists():
        return

    unexpected_modules = sorted(
        path.relative_to(ROOT).as_posix()
        for path in db_migrations_dir.glob("*.py")
        if path.name != "__init__.py"
    )

    assert unexpected_modules == []


def test_runtime_migration_entrypoint_uses_cli_migration_runner() -> None:
    bootstrap = _read("app/db/runtime/bootstrap.py")
    migrate_db = _read("app/cli/migrate_db.py")

    assert "app.cli.migrations.migration_runner" in bootstrap
    assert "DatabaseSessionManager" in migrate_db
    assert "app.db.migrations.migration_runner" not in bootstrap


def test_active_web_contracts_do_not_use_carbon_client_id() -> None:
    checked_paths = [
        "clients/web/src/api/auth.ts",
        "clients/web/src/features/auth/SecretLoginForm.tsx",
        "clients/web/src/api/auth.test.ts",
        "clients/web/src/tests/e2e/web-smoke.spec.ts",
        "docs/reference/frontend-web.md",
        "docs/SPEC.md",
    ]

    offenders = [
        relative_path for relative_path in checked_paths if "web-carbon-v1" in _read(relative_path)
    ]

    assert offenders == []


def test_monitoring_alert_names_use_ratatoskr_prefix() -> None:
    alerting_rules = _read("ops/monitoring/alerting_rules.yml")

    assert "alert: BSR" not in alerting_rules


def test_deployment_docs_match_current_firecrawl_compose_shape() -> None:
    compose = _read("ops/docker/docker-compose.yml")
    deployment = _read("docs/DEPLOYMENT.md")
    scraper_adr = _read("docs/adr/0006-multi-provider-scraper-chain.md")

    compose_has_firecrawl_service = "\n  firecrawl" in compose
    if compose_has_firecrawl_service:
        return

    forbidden_claims = [
        "Docker Compose includes a `ratatoskr-firecrawl` service",
        "`ratatoskr-firecrawl` service",
        "port 3002",
        "Self-hosted Firecrawl services in `ops/docker/docker-compose.yml`",
    ]

    offenders = [claim for claim in forbidden_claims if claim in deployment or claim in scraper_adr]

    assert offenders == []


def test_generated_requirement_comments_use_current_project_name() -> None:
    requirements = _read("requirements-all.txt")

    assert "via bite-size-reader" not in requirements
    assert "#   bite-size-reader" not in requirements
