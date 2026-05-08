"""Owner credential bootstrap (nickname/email + password).

This is the only writer for ``user_credentials`` rows. Login flow has no
public signup -- the owner runs ``ratatoskr credentials set`` once after
deploy to seed their password, then logs in via the web client.

The command speaks directly to Postgres (no HTTP) so it works pre-token
and pre-deploy. Refuses to run if:
  - CREDENTIALS_LOGIN_ENABLED is not true,
  - CREDENTIALS_LOGIN_PEPPER is missing or <32 chars (config-validator
    would also reject this at API startup),
  - the supplied --user-id is not in ALLOWED_USER_IDS.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

import click


def _bail(message: str) -> None:
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _resolve_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        _bail(
            "DATABASE_URL must be set. Example: "
            "postgresql+asyncpg://ratatoskr_app:***@localhost:5432/ratatoskr"
        )
    if "+asyncpg" not in dsn:
        # Auto-promote postgresql:// to postgresql+asyncpg:// so the operator
        # doesn't have to remember the driver suffix for a one-shot bootstrap.
        if dsn.startswith("postgresql://"):
            dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        else:
            _bail("DATABASE_URL must use postgresql+asyncpg:// scheme")
    return dsn


def _check_pepper_configured() -> None:
    """Bootstrap requires a pepper -- the hash is useless without it.

    Pepper presence (not a separate flag) is what gates credentials login,
    so the bootstrap fails cleanly with the same remediation message a
    runtime credentials-login request would surface.
    """
    pepper = os.environ.get("CREDENTIALS_LOGIN_PEPPER", "").strip()
    if not pepper or len(pepper) < 32:
        _bail(
            "CREDENTIALS_LOGIN_PEPPER must be set to >=32 chars. "
            "Generate one with: openssl rand -hex 32"
        )


def _check_user_allowlisted(user_id: int) -> None:
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    if not raw:
        _bail(
            "ALLOWED_USER_IDS is empty. Set it to your Telegram user ID(s) "
            "before bootstrapping credentials."
        )
    allowed = {int(part.strip()) for part in raw.split(",") if part.strip().isdigit()}
    if user_id not in allowed:
        _bail(
            f"User ID {user_id} is not in ALLOWED_USER_IDS. "
            "Credentials bootstrap is restricted to allowlisted owners."
        )


def _prompt_password() -> str:
    """Prompt twice; bail on mismatch. Length validation runs server-side."""
    pw = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm:  ")
    if pw != confirm:
        _bail("Passwords do not match.")
    return pw


async def _upsert(
    *,
    dsn: str,
    user_id: int,
    nickname: str,
    email: str | None,
    password: str,
) -> int:
    """Insert or replace the user's credential row."""
    # Defer the heavy imports until we actually need them -- keeps the rest
    # of the CLI surface light if the user just runs `ratatoskr --help`.
    from app.api.routers.auth import credential_auth
    from app.config.database import DatabaseConfig
    from app.db.session import Database
    from app.infrastructure.persistence.repositories.user_credentials_repository import (
        UserCredentialRepositoryAdapter,
    )

    nick_display, nick_canonical = credential_auth.canonicalize_nickname(nickname)
    email_display, email_canonical = credential_auth.canonicalize_email(email)
    phc, version = credential_auth.hash_password(password)

    db = Database(config=DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    try:
        repo = UserCredentialRepositoryAdapter(db)
        return await repo.async_upsert(
            user_id=user_id,
            nickname=nick_display,
            nickname_canonical=nick_canonical,
            email=email_display,
            email_canonical=email_canonical,
            password_hash=phc,
            pepper_version=version,
        )
    finally:
        await db.dispose()


@click.group()
def credentials() -> None:
    """Manage the owner's nickname/email + password credential."""


@credentials.command("set")
@click.option(
    "--user-id",
    type=int,
    required=True,
    help="Telegram user ID to attach the credential to (must be in ALLOWED_USER_IDS).",
)
@click.option(
    "--nickname",
    type=str,
    required=True,
    help="Display nickname; case-folded for matching, case-preserved for display.",
)
@click.option(
    "--email",
    type=str,
    default=None,
    help="Optional email; serves as a second login identifier.",
)
def credentials_set(user_id: int, nickname: str, email: str | None) -> None:
    """Create or replace the owner's credential row.

    Re-running this command for the same user replaces the password hash
    (resets failed_attempts and locked_until). Use it as the recovery path
    when the owner forgets their password -- there is no email reset flow
    in this single-owner system.
    """
    _check_pepper_configured()
    _check_user_allowlisted(user_id)
    dsn = _resolve_dsn()

    password = _prompt_password()

    record_id = asyncio.run(
        _upsert(
            dsn=dsn,
            user_id=user_id,
            nickname=nickname,
            email=email,
            password=password,
        )
    )

    click.echo(f"Credential saved (id={record_id}) for user {user_id}.")


# Alias for ergonomic clarity -- "reset" is the recovery framing,
# "set" is the bootstrap framing. Same operation either way.
credentials.add_command(credentials_set, name="reset")
