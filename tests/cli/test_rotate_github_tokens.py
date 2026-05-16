"""Tests for app.cli.rotate_github_tokens."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from app.security.token_crypto import reset_key_cache


@pytest.fixture(autouse=True)
def _reset_crypto_cache():
    # Pre-reset is the real protection against cross-test cache pollution.
    reset_key_cache()
    yield
    reset_key_cache()


def _make_row(user_id: int, encrypted_token: bytes) -> MagicMock:
    row = MagicMock()
    row.id = user_id
    row.user_id = user_id
    row.encrypted_token = encrypted_token
    return row


def _import_reencrypt():
    from app.cli.rotate_github_tokens import reencrypt_all_tokens

    return reencrypt_all_tokens


@pytest.mark.asyncio
async def test_reencrypt_row_encrypted_with_old_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row encrypted with an old key is re-encrypted with the primary key."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ct = Fernet(old_key).encrypt(b"ghp_secret")
    row = _make_row(1, old_ct)

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", old_key.decode("ascii"))

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    session.get = AsyncMock(return_value=row)
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)
    db.transaction.return_value.__aenter__ = AsyncMock(return_value=session)
    db.transaction.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=False)

    assert result.processed == 1
    assert result.reencrypted == 1
    assert result.failed == 0
    # Verify the stored ciphertext is now readable by the primary key alone
    new_ct = row.encrypted_token
    assert Fernet(new_key).decrypt(new_ct) == b"ghp_secret"


@pytest.mark.asyncio
async def test_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """dry_run=True reports would-be changes but does not open a transaction."""
    key = Fernet.generate_key()
    ct = Fernet(key).encrypt(b"ghp_dryrun")
    row = _make_row(2, ct)
    original_ct = ct

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=True)

    assert result.processed == 1
    assert result.reencrypted == 1
    assert result.failed == 0
    # No transaction opened in dry-run mode
    db.transaction.assert_not_called()
    # Row object is unchanged
    assert row.encrypted_token == original_ct


@pytest.mark.asyncio
async def test_undecryptable_row_counted_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row with garbage ciphertext is logged and counted as failed — loop continues."""
    new_key = Fernet.generate_key()
    row = _make_row(3, b"this is not valid fernet ciphertext")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=False)

    assert result.processed == 1
    assert result.reencrypted == 0
    assert result.failed == 1


@pytest.mark.asyncio
async def test_user_id_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_id parameter restricts which rows are fetched."""
    key = Fernet.generate_key()
    ct = Fernet(key).encrypt(b"ghp_filtered")
    row = _make_row(42, ct)

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))
        )
    )
    session.get = AsyncMock(return_value=row)
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)
    db.transaction.return_value.__aenter__ = AsyncMock(return_value=session)
    db.transaction.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=False, user_id=42)

    assert result.processed == 1
    assert result.reencrypted == 1
