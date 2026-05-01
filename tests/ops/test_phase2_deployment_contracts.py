from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "ops/docker/docker-compose.yml").read_text(encoding="utf-8"))


def _env_map(service: dict[str, Any]) -> dict[str, str]:
    environment = service.get("environment", {})
    if isinstance(environment, dict):
        return {str(key): str(value) for key, value in environment.items()}
    result: dict[str, str] = {}
    for item in environment:
        key, _, value = str(item).partition("=")
        result[key] = value
    return result


def test_default_compose_stack_contains_core_services_without_profiles() -> None:
    services = _compose()["services"]

    for name in ("ratatoskr", "mobile-api", "redis", "chroma"):
        assert name in services
        assert "profiles" not in services[name]

    assert services["mobile-api"]["ports"] == ["127.0.0.1:18000:8000"]


def test_scrapers_profile_uses_internal_services_not_host_gateway() -> None:
    services = _compose()["services"]

    assert "extra_hosts" not in services["ratatoskr"]
    ratatoskr_env = _env_map(services["ratatoskr"])
    assert (
        ratatoskr_env["FIRECRAWL_SELF_HOSTED_URL"]
        == "${FIRECRAWL_SELF_HOSTED_URL:-http://firecrawl-api:3002}"
    )

    for name in (
        "firecrawl-api",
        "firecrawl-playwright",
        "firecrawl-redis",
        "firecrawl-rabbitmq",
        "firecrawl-postgres",
    ):
        assert name in services
        assert services[name]["profiles"] == ["with-scrapers"]

    assert services["firecrawl-api"]["depends_on"]["firecrawl-playwright"]["condition"]
    assert "3002" in services["firecrawl-api"]["ports"][0]


def test_cloud_ollama_profile_does_not_start_local_ollama() -> None:
    services = _compose()["services"]

    ollama_services = [name for name in services if "ollama" in name]
    assert ollama_services == ["cloud-ollama-check"]
    assert services["cloud-ollama-check"]["profiles"] == ["with-cloud-ollama"]

    ratatoskr_env = _env_map(services["ratatoskr"])
    assert ratatoskr_env["LLM_PROVIDER"] == "${LLM_PROVIDER:-openrouter}"
    assert ratatoskr_env["OLLAMA_BASE_URL"] == "${OLLAMA_BASE_URL:-http://localhost:11434/v1}"


def test_monitoring_profile_is_in_primary_compose_file() -> None:
    services = _compose()["services"]

    for name in ("prometheus", "grafana", "loki", "promtail", "node-exporter"):
        assert name in services
        assert services[name]["profiles"] == ["with-monitoring"]


def test_release_workflow_publishes_stable_but_not_latest() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
    tags = workflow["jobs"]["push-docker-tag"]["steps"][4]["with"]["tags"]

    assert "type=raw,value=stable" in tags
    assert "latest" not in tags
