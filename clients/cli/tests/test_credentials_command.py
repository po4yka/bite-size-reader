"""Tests for the `ratatoskr credentials` CLI subcommand."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from ratatoskr_cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def env_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip credential-related env vars so each test starts blank."""
    for name in (
        "CREDENTIALS_LOGIN_PEPPER",
        "ALLOWED_USER_IDS",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


# ---------- Discovery / wiring ----------


def test_credentials_group_is_registered(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["credentials", "--help"])
    assert result.exit_code == 0
    assert "set" in result.output
    assert "reset" in result.output


def test_set_help_shows_required_flags(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["credentials", "set", "--help"])
    assert result.exit_code == 0
    assert "--user-id" in result.output
    assert "--nickname" in result.output
    assert "--email" in result.output


def test_set_missing_required_flags_fails(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["credentials", "set"])
    assert result.exit_code != 0


# ---------- Fail-closed gates (no DB required) ----------


def test_set_refuses_when_pepper_missing(runner: CliRunner, env_clean: None) -> None:
    """Pepper presence is the only gate -- no separate feature flag exists."""
    result = runner.invoke(
        cli,
        ["credentials", "set", "--user-id", "42", "--nickname", "owner"],
    )
    assert result.exit_code == 1
    assert "CREDENTIALS_LOGIN_PEPPER" in result.output


def test_set_refuses_when_pepper_too_short(
    runner: CliRunner, env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CREDENTIALS_LOGIN_PEPPER", "tooshort")
    result = runner.invoke(
        cli,
        ["credentials", "set", "--user-id", "42", "--nickname", "owner"],
    )
    assert result.exit_code == 1
    assert "CREDENTIALS_LOGIN_PEPPER" in result.output


def test_set_refuses_when_user_not_allowlisted(
    runner: CliRunner, env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CREDENTIALS_LOGIN_PEPPER", "x" * 32)
    monkeypatch.setenv("ALLOWED_USER_IDS", "999999")
    result = runner.invoke(
        cli,
        ["credentials", "set", "--user-id", "42", "--nickname", "owner"],
    )
    assert result.exit_code == 1
    assert "ALLOWED_USER_IDS" in result.output


def test_set_refuses_when_database_url_missing(
    runner: CliRunner, env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CREDENTIALS_LOGIN_PEPPER", "x" * 32)
    monkeypatch.setenv("ALLOWED_USER_IDS", "42")
    # Stub getpass so the command reaches the DSN check (it would otherwise
    # hang waiting for input on the password prompt).
    with patch("ratatoskr_cli.commands.credentials.getpass.getpass", return_value="pw"):
        result = runner.invoke(
            cli,
            ["credentials", "set", "--user-id", "42", "--nickname", "owner"],
        )
    assert result.exit_code == 1
    assert "DATABASE_URL" in result.output


# ---------- Password-prompt mismatch ----------


def test_set_bails_when_passwords_do_not_match(
    runner: CliRunner, env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CREDENTIALS_LOGIN_PEPPER", "x" * 32)
    monkeypatch.setenv("ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")

    with patch(
        "ratatoskr_cli.commands.credentials.getpass.getpass",
        side_effect=["password-one", "password-two"],
    ):
        result = runner.invoke(
            cli,
            ["credentials", "set", "--user-id", "42", "--nickname", "owner"],
        )
    assert result.exit_code == 1
    assert "do not match" in result.output


# ---------- Round-trip against real Postgres ----------


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for the DB round-trip",
)
def test_set_writes_credential_row(
    runner: CliRunner, env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: command writes a row that the login flow can verify against."""
    import asyncio

    from app.api.routers.auth import credential_auth
    from app.config.database import DatabaseConfig
    from app.db.session import Database
    from app.infrastructure.persistence.repositories.user_credentials_repository import (
        UserCredentialRepositoryAdapter,
    )

    dsn = os.environ["TEST_DATABASE_URL"]

    async def setup_user_and_truncate() -> None:
        db = Database(config=DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
        await db.migrate()
        from sqlalchemy import text

        async with db.transaction() as session:
            await session.execute(
                text('TRUNCATE TABLE "user_credentials", "users" RESTART IDENTITY CASCADE')
            )
        # Owner row is required by the FK.
        from app.db.models import User

        async with db.transaction() as session:
            session.add(User(telegram_user_id=42, username="owner", is_owner=True))
        await db.dispose()

    asyncio.run(setup_user_and_truncate())

    monkeypatch.setenv("CREDENTIALS_LOGIN_PEPPER", "x" * 32)
    monkeypatch.setenv("ALLOWED_USER_IDS", "42")
    monkeypatch.setenv("DATABASE_URL", dsn)
    # argon2 cost knobs -- keep the test fast.
    monkeypatch.setenv("CREDENTIALS_LOGIN_ARGON2_TIME_COST", "1")
    monkeypatch.setenv("CREDENTIALS_LOGIN_ARGON2_MEMORY_KIB", "8192")
    # The credential bootstrap calls into load_config(), which validates the
    # full app config. Provide stubs for the otherwise-required keys.
    monkeypatch.setenv("API_ID", "1")
    monkeypatch.setenv("API_HASH", "test_api_hash_placeholder_value___")
    monkeypatch.setenv("BOT_TOKEN", "1000000000:TESTTOKENPLACEHOLDER1234567890ABC")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "dummy-firecrawl-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-openrouter-key")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-at-least-32-chars-long-string")
    monkeypatch.setenv("REDIS_ENABLED", "0")
    # Reset the credential_auth caches so the test env wins.
    credential_auth._cfg = None
    credential_auth._hasher = None
    credential_auth._DECOY_PHC = None

    new_password = "correct horse battery staple"
    with patch(
        "ratatoskr_cli.commands.credentials.getpass.getpass",
        side_effect=[new_password, new_password],
    ):
        result = runner.invoke(
            cli,
            [
                "credentials",
                "set",
                "--user-id",
                "42",
                "--nickname",
                "Owner",
                "--email",
                "owner@example.com",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "Credential saved" in result.output

    async def fetch_and_verify() -> None:
        db = Database(config=DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
        try:
            repo = UserCredentialRepositoryAdapter(db)
            row = await repo.async_get_by_user_id(42)
            assert row is not None
            assert row["nickname"] == "Owner"
            assert row["nickname_canonical"] == "owner"
            assert row["email_canonical"] == "owner@example.com"
            ok, _ = credential_auth.verify_password(
                new_password, row["password_hash"], row["pepper_version"]
            )
            assert ok
        finally:
            await db.dispose()

    asyncio.run(fetch_and_verify())
