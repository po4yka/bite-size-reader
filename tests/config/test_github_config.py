"""Tests for GitHubConfig."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from app.config.github import GitHubConfig


def test_defaults_load_when_no_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "GITHUB_REQUEST_TIMEOUT_SEC",
        "GITHUB_README_MAX_BYTES",
        "GITHUB_SYNC_ENABLED",
        "GITHUB_SYNC_CRON",
        "GITHUB_SYNC_LLM_CONCURRENCY",
        "GITHUB_SYNC_LLM_DAILY_BUDGET",
        "GITHUB_OAUTH_APP_CLIENT_ID",
        "GITHUB_OAUTH_APP_CLIENT_SECRET",
        "GITHUB_TOKEN_ENCRYPTION_KEY",
        "GITHUB_CONCURRENCY_PER_USER",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = GitHubConfig()
    assert cfg.request_timeout_sec == 30.0
    assert cfg.readme_max_bytes == 51200
    assert cfg.sync_enabled is True
    assert cfg.sync_cron == "0 2 * * *"
    assert cfg.llm_concurrency == 2
    assert cfg.llm_daily_budget == 100
    assert cfg.oauth_app_client_id is None


def test_env_vars_override_defaults() -> None:
    # GitHubConfig is a BaseModel (not BaseSettings); env vars are wired via
    # Settings._build_nested_from_env using validation_alias. Test the alias
    # round-trip by constructing with the alias keys directly.
    cfg = GitHubConfig.model_validate(
        {
            "GITHUB_SYNC_ENABLED": False,
            "GITHUB_SYNC_LLM_DAILY_BUDGET": 50,
            "GITHUB_OAUTH_APP_CLIENT_ID": "iv1.abc",
        }
    )
    assert cfg.sync_enabled is False
    assert cfg.llm_daily_budget == 50
    assert cfg.oauth_app_client_id == "iv1.abc"


def test_appconfig_includes_github_subconfig() -> None:
    from app.config.settings import AppConfig

    assert "github" in AppConfig.__dataclass_fields__
