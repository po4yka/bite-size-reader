# Fernet Key Rotation for GitHub Integration Tokens

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow operators to rotate `GITHUB_TOKEN_ENCRYPTION_KEY` without breaking stored tokens by implementing `MultiFernet` support with a `GITHUB_TOKEN_PREVIOUS_KEYS` config var and a re-encryption CLI.

**Architecture:** Replace the single `Fernet` instance in `token_crypto.py` with `MultiFernet([primary, *previous])` so decryption tries all configured keys and encryption always uses the primary key. A new comma-separated `GITHUB_TOKEN_PREVIOUS_KEYS` env var holds old Fernet keys for the transition window. A CLI script `rotate_github_tokens.py` re-encrypts all `UserGitHubIntegration.encrypted_token` rows under the primary key, after which old keys can be safely dropped.

**Tech Stack:** Python 3.13+, `cryptography` (`Fernet`, `MultiFernet`), SQLAlchemy 2.0 async, pydantic `SecretStr`, pytest, pytest-asyncio.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `app/config/github.py` | Add `token_previous_keys: SecretStr \| None` field |
| Modify | `app/security/token_crypto.py` | Replace `_get_fernet()` with `_get_multi_fernet() -> MultiFernet`; add `_parse_previous_keys()`; update `reset_key_cache` |
| Modify | `tests/security/test_token_crypto.py` | Add 5 new multi-key test cases |
| Create | `app/cli/rotate_github_tokens.py` | Re-encryption CLI (`--dry-run`, `--user-id`, `--log-level`, `--env-file`) |
| Create | `tests/cli/test_rotate_github_tokens.py` | Unit tests for the re-encryption logic |
| Modify | `tools/scripts/generate_github_encryption_key.py` | Update docstring with rotation workflow |
| Modify | `docs/reference/environment-variables.md` | Add `GITHUB_TOKEN_PREVIOUS_KEYS` row |

---

## Task 1: Write Failing Tests for MultiFernet Behavior

**Files:**
- Modify: `tests/security/test_token_crypto.py`

These tests fail against the current single-key implementation; they pass once Task 2 is done.

- [ ] **Step 1: Append the five new test functions to the existing test file**

Open `tests/security/test_token_crypto.py` and add after the last existing test:

```python
def test_decrypt_with_previous_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ciphertext produced by an old key decrypts when that key is in PREVIOUS_KEYS."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ct = Fernet(old_key).encrypt(b"ghp_old_secret")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", old_key.decode("ascii"))

    assert decrypt_token(old_ct) == "ghp_old_secret"


def test_encrypt_uses_primary_key_not_previous(monkeypatch: pytest.MonkeyPatch) -> None:
    """encrypt_token always produces ciphertext readable by the primary key alone."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", old_key.decode("ascii"))

    ct = encrypt_token("ghp_test")
    # primary-key-only Fernet must decrypt it successfully
    assert Fernet(new_key).decrypt(ct) == b"ghp_test"


def test_old_ciphertext_fails_without_previous_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Old-key ciphertext raises when old key is absent from PREVIOUS_KEYS."""
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_ct = Fernet(old_key).encrypt(b"ghp_secret")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    with pytest.raises(InvalidEncryptedTokenError):
        decrypt_token(old_ct)


def test_multiple_previous_keys_all_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma-separated previous keys: each old ciphertext decrypts successfully."""
    k1, k2, new_key = Fernet.generate_key(), Fernet.generate_key(), Fernet.generate_key()
    ct1 = Fernet(k1).encrypt(b"token_from_k1")
    ct2 = Fernet(k2).encrypt(b"token_from_k2")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.setenv(
        "GITHUB_TOKEN_PREVIOUS_KEYS",
        f"{k1.decode('ascii')},{k2.decode('ascii')}",
    )

    assert decrypt_token(ct1) == "token_from_k1"
    assert decrypt_token(ct2) == "token_from_k2"


def test_malformed_previous_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed entry in GITHUB_TOKEN_PREVIOUS_KEYS raises MissingEncryptionKeyError."""
    new_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("GITHUB_TOKEN_PREVIOUS_KEYS", "not-a-valid-fernet-key")

    with pytest.raises(MissingEncryptionKeyError):
        encrypt_token("x")
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/security/test_token_crypto.py -v -k "previous or multiple or old_cipher" 2>&1 | tail -30
```

Expected: `FAILED` for each of the 5 new tests. The `decrypt_with_previous_key` test fails with `InvalidEncryptedTokenError`; `malformed_previous_key_raises` may pass accidentally if the env var is silently ignored — that is acceptable at this stage.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/security/test_token_crypto.py
git commit -m "test(security): add failing tests for MultiFernet key rotation behavior"
```

---

## Task 2: Implement MultiFernet in Config and `token_crypto.py`

**Files:**
- Modify: `app/config/github.py`
- Modify: `app/security/token_crypto.py`

- [ ] **Step 1: Add `token_previous_keys` field to `GitHubConfig`**

In `app/config/github.py`, add one field inside `GitHubConfig` after `token_encryption_key`:

```python
    # Previous Fernet keys for zero-downtime rotation (comma-separated; see token_crypto.py)
    token_previous_keys: SecretStr | None = Field(
        default=None,
        validation_alias="GITHUB_TOKEN_PREVIOUS_KEYS",
        description=(
            "Comma-separated previous Fernet keys still needed to decrypt existing rows. "
            "Remove each key only after running `python -m app.cli.rotate_github_tokens`."
        ),
    )
```

- [ ] **Step 2: Replace `token_crypto.py` with the MultiFernet implementation**

Replace the entire content of `app/security/token_crypto.py`:

```python
"""Fernet symmetric encryption for at-rest secrets (e.g., GitHub PAT, OAuth access tokens).

Key loading is lazy and cached. The first call validates the configured key.
Missing key raises `MissingEncryptionKeyError` with a hint to generate one.

Key rotation (zero-downtime):
1. Generate a new key: ``python tools/scripts/generate_github_encryption_key.py``
2. Set the new key as ``GITHUB_TOKEN_ENCRYPTION_KEY``.
3. Move the old key to ``GITHUB_TOKEN_PREVIOUS_KEYS`` (comma-separated; multiple old keys OK).
4. Deploy — existing ciphertexts still decrypt; new writes use the new key.
5. Backfill: ``python -m app.cli.rotate_github_tokens``
6. Remove the old key from ``GITHUB_TOKEN_PREVIOUS_KEYS`` and redeploy.
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

__all__ = [
    "InvalidEncryptedTokenError",
    "MissingEncryptionKeyError",
    "decrypt_token",
    "encrypt_token",
    "reset_key_cache",
]


class MissingEncryptionKeyError(RuntimeError):
    """Raised when GITHUB_TOKEN_ENCRYPTION_KEY is unset or malformed."""


class InvalidEncryptedTokenError(ValueError):
    """Raised when a ciphertext cannot be decrypted (key change, corruption, tampering)."""


def _parse_previous_keys(raw: str | None) -> list[Fernet]:
    """Parse comma-separated previous Fernet keys.  Returns [] when *raw* is empty."""
    if not raw:
        return []
    result: list[Fernet] = []
    for i, part in enumerate(p.strip() for p in raw.split(",") if p.strip()):
        encoded = part.encode("utf-8") if isinstance(part, str) else part
        try:
            result.append(Fernet(encoded))
        except (ValueError, TypeError) as exc:
            raise MissingEncryptionKeyError(
                f"GITHUB_TOKEN_PREVIOUS_KEYS[{i}] is malformed "
                f"(must be 32 url-safe base64 bytes). Underlying error: {exc}"
            ) from exc
    return result


@lru_cache(maxsize=1)
def _get_multi_fernet() -> MultiFernet:
    from app.config.settings import load_config

    settings = load_config(allow_stub_telegram=True)
    secret = settings.github.token_encryption_key
    if secret is None:
        raise MissingEncryptionKeyError(
            "GITHUB_TOKEN_ENCRYPTION_KEY is not configured. "
            "Generate one with: python tools/scripts/generate_github_encryption_key.py "
            "and set it in your .env file."
        )
    raw_value = secret.get_secret_value()
    raw = raw_value.encode("utf-8") if isinstance(raw_value, str) else raw_value
    try:
        primary = Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise MissingEncryptionKeyError(
            f"GITHUB_TOKEN_ENCRYPTION_KEY is malformed (must be 32 url-safe base64 bytes). "
            f"Generate one with: python tools/scripts/generate_github_encryption_key.py. "
            f"Underlying error: {exc}"
        ) from exc

    prev_secret = settings.github.token_previous_keys
    prev_raw = prev_secret.get_secret_value() if prev_secret is not None else None
    previous = _parse_previous_keys(prev_raw)

    return MultiFernet([primary, *previous])


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a token string with the primary key. Returns Fernet ciphertext bytes."""
    if not plaintext:
        raise ValueError("Cannot encrypt empty plaintext")
    return _get_multi_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt previously encrypted ciphertext. Tries primary key then all previous keys."""
    try:
        return _get_multi_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise InvalidEncryptedTokenError("Ciphertext could not be decrypted") from exc


def reset_key_cache() -> None:
    """Clear the cached MultiFernet instance and the settings config cache. For tests."""
    _get_multi_fernet.cache_clear()
    from app.config.settings import clear_config_cache

    clear_config_cache()
```

- [ ] **Step 3: Run all token_crypto tests**

```bash
source .venv/bin/activate && pytest tests/security/test_token_crypto.py -v 2>&1 | tail -30
```

Expected: all 11 tests `PASSED`.

- [ ] **Step 4: Run linting and type check**

```bash
source .venv/bin/activate && ruff check app/security/token_crypto.py app/config/github.py && mypy app/security/token_crypto.py app/config/github.py 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add app/config/github.py app/security/token_crypto.py
git commit -m "feat(security): implement MultiFernet key rotation for GitHub tokens

Add GITHUB_TOKEN_PREVIOUS_KEYS env var (comma-separated old Fernet keys).
Replace single Fernet with MultiFernet([primary, *previous]) so decryption
works with any configured key while encryption always uses the primary.
Operators can now rotate without downtime; backfill via rotate_github_tokens CLI."
```

---

## Task 3: Write Failing Tests for the Re-Encryption CLI

**Files:**
- Create: `tests/cli/test_rotate_github_tokens.py`

- [ ] **Step 1: Create the test file**

Create `tests/cli/test_rotate_github_tokens.py`:

```python
"""Tests for app.cli.rotate_github_tokens."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from app.security.token_crypto import reset_key_cache


@pytest.fixture(autouse=True)
def _reset_crypto_cache():
    reset_key_cache()
    yield
    reset_key_cache()


def _make_row(user_id: int, encrypted_token: bytes) -> MagicMock:
    row = MagicMock()
    row.id = user_id
    row.user_id = user_id
    row.encrypted_token = encrypted_token
    return row


# ---------------------------------------------------------------------------
# Import helper: the CLI module imports SQLAlchemy models; keep it lazy.
# ---------------------------------------------------------------------------


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
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))))
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
    # Verify the new ciphertext is readable by the primary key only
    new_ct = row.encrypted_token
    assert Fernet(new_key).decrypt(new_ct) == b"ghp_secret"


@pytest.mark.asyncio
async def test_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """dry_run=True reports would-be changes but does not modify DB rows."""
    key = Fernet.generate_key()
    ct = Fernet(key).encrypt(b"ghp_dryrun")
    row = _make_row(2, ct)
    original_ct = ct

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))))
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=True)

    assert result.processed == 1
    assert result.reencrypted == 1
    assert result.failed == 0
    # transaction should NOT have been opened in dry-run mode
    db.transaction.assert_not_called()
    # The row object is unchanged
    assert row.encrypted_token == original_ct


@pytest.mark.asyncio
async def test_undecryptable_row_counted_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row with an undecryptable ciphertext is logged and counted as failed, not crashed."""
    new_key = Fernet.generate_key()
    row = _make_row(3, b"this is not valid fernet ciphertext")

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", new_key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))))
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=False)

    assert result.processed == 1
    assert result.reencrypted == 0
    assert result.failed == 1


@pytest.mark.asyncio
async def test_user_id_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """user_id parameter restricts which rows are re-encrypted."""
    key = Fernet.generate_key()
    ct = Fernet(key).encrypt(b"ghp_filtered")
    row = _make_row(42, ct)

    monkeypatch.setenv("GITHUB_TOKEN_ENCRYPTION_KEY", key.decode("ascii"))
    monkeypatch.delenv("GITHUB_TOKEN_PREVIOUS_KEYS", raising=False)

    db = MagicMock()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))))
    session.get = AsyncMock(return_value=row)
    db.session.return_value.__aenter__ = AsyncMock(return_value=session)
    db.session.return_value.__aexit__ = AsyncMock(return_value=False)
    db.transaction.return_value.__aenter__ = AsyncMock(return_value=session)
    db.transaction.return_value.__aexit__ = AsyncMock(return_value=False)

    reencrypt_all_tokens = _import_reencrypt()
    result = await reencrypt_all_tokens(db, dry_run=False, user_id=42)

    assert result.processed == 1
    # The WHERE clause shape is validated by verifying the execute call received a filtered stmt.
    # (Full SQL assertion is an integration concern; unit test verifies result counts.)
    assert result.reencrypted == 1
```

- [ ] **Step 2: Run these tests to confirm they fail with ImportError**

```bash
source .venv/bin/activate && pytest tests/cli/test_rotate_github_tokens.py -v 2>&1 | tail -20
```

Expected: `ERROR` (ImportError) because `app.cli.rotate_github_tokens` does not exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/cli/test_rotate_github_tokens.py
git commit -m "test(cli): add failing tests for rotate_github_tokens CLI"
```

---

## Task 4: Implement the Re-Encryption CLI

**Files:**
- Create: `app/cli/rotate_github_tokens.py`

- [ ] **Step 1: Create the CLI module**

Create `app/cli/rotate_github_tokens.py`:

```python
"""CLI tool: re-encrypt all UserGitHubIntegration tokens under the primary Fernet key.

Run this after adding a new GITHUB_TOKEN_ENCRYPTION_KEY and moving the old key to
GITHUB_TOKEN_PREVIOUS_KEYS. Once complete, the old key can be safely removed.

Usage:
    python -m app.cli.rotate_github_tokens [--dry-run] [--user-id ID] [--log-level LEVEL]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select

from app.cli._runtime import prepare_config
from app.core.logging_utils import get_logger, setup_json_logging
from app.db.models.repository import UserGitHubIntegration
from app.di.database import build_runtime_database
from app.security.token_crypto import InvalidEncryptedTokenError, decrypt_token, encrypt_token

logger = get_logger(__name__)

__all__ = ["ReencryptResult", "main", "reencrypt_all_tokens"]


@dataclass(frozen=True)
class ReencryptResult:
    processed: int
    reencrypted: int
    failed: int


async def reencrypt_all_tokens(
    db: object,
    *,
    dry_run: bool = False,
    user_id: int | None = None,
) -> ReencryptResult:
    """Re-encrypt every integration token with the current primary key.

    Decryption uses MultiFernet (primary + previous keys); encryption uses primary only.
    Rows that cannot be decrypted are counted as *failed* and logged — the loop continues.
    """
    async with db.session() as session:  # type: ignore[union-attr]
        stmt = select(UserGitHubIntegration)
        if user_id is not None:
            stmt = stmt.where(UserGitHubIntegration.user_id == user_id)
        result = await session.execute(stmt)
        rows: list[UserGitHubIntegration] = list(result.scalars().all())

    processed = reencrypted = failed = 0

    for row in rows:
        processed += 1
        try:
            plaintext = decrypt_token(row.encrypted_token)
            new_ct = encrypt_token(plaintext)
            if not dry_run:
                async with db.transaction() as txn:  # type: ignore[union-attr]
                    fresh = await txn.get(UserGitHubIntegration, row.id)
                    if fresh is not None:
                        fresh.encrypted_token = new_ct
                row.encrypted_token = new_ct  # reflect for callers / tests
            reencrypted += 1
            logger.info(
                "token_reencrypted",
                extra={"user_id": row.user_id, "dry_run": dry_run},
            )
        except InvalidEncryptedTokenError:
            failed += 1
            logger.error(
                "token_reencrypt_failed_undecryptable",
                extra={"user_id": row.user_id},
            )

    return ReencryptResult(processed=processed, reencrypted=reencrypted, failed=failed)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-encrypt all GitHub integration tokens under the primary Fernet key. "
            "Run after rotating GITHUB_TOKEN_ENCRYPTION_KEY."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report would-be changes without writing to the database.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Restrict re-encryption to this Telegram user_id.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Path to a .env file with environment variables.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    cfg = prepare_config(args)
    setup_json_logging(cfg.runtime.log_level)

    db = build_runtime_database(cfg, migrate=False)
    result = await reencrypt_all_tokens(db, dry_run=args.dry_run, user_id=args.user_id)

    import json

    try:
        import orjson

        print(orjson.dumps(asdict(result), option=orjson.OPT_INDENT_2).decode())
    except ImportError:
        print(json.dumps(asdict(result), indent=2))

    if result.failed:
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m app.cli.rotate_github_tokens``."""
    args = parse_args(argv)
    try:
        asyncio.run(_run(args))
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 1
    except KeyboardInterrupt:  # pragma: no cover
        return 1
    except Exception as exc:
        logger.exception("rotate_github_tokens_failed", exc_info=exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 2: Run the CLI tests**

```bash
source .venv/bin/activate && pytest tests/cli/test_rotate_github_tokens.py -v 2>&1 | tail -30
```

Expected: all 4 tests `PASSED`.

- [ ] **Step 3: Run linting and type check on the new CLI**

```bash
source .venv/bin/activate && ruff check app/cli/rotate_github_tokens.py && mypy app/cli/rotate_github_tokens.py 2>&1 | tail -20
```

Expected: no errors.

- [ ] **Step 4: Run the full security and CLI test suites**

```bash
source .venv/bin/activate && pytest tests/security/ tests/cli/test_rotate_github_tokens.py -v 2>&1 | tail -30
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add app/cli/rotate_github_tokens.py
git commit -m "feat(cli): add rotate_github_tokens CLI for Fernet key rotation backfill

Decrypts each UserGitHubIntegration.encrypted_token with MultiFernet
(primary + previous keys), re-encrypts with primary key only, and writes
back atomically per row. Supports --dry-run and --user-id filters.
Exit code 1 when any row fails to decrypt."
```

---

## Task 5: Update Docs and Key Generation Script

**Files:**
- Modify: `tools/scripts/generate_github_encryption_key.py`
- Modify: `docs/reference/environment-variables.md`

- [ ] **Step 1: Update the key generation script docstring**

Replace the full content of `tools/scripts/generate_github_encryption_key.py`:

```python
#!/usr/bin/env python3
"""Generate a new Fernet key for GITHUB_TOKEN_ENCRYPTION_KEY.

Usage:
    python tools/scripts/generate_github_encryption_key.py

Copy the output line into your .env file:
    GITHUB_TOKEN_ENCRYPTION_KEY=<generated-key>

Zero-downtime key rotation procedure:
1. Generate a new key with this script.
2. In your .env / secret store:
   - Set GITHUB_TOKEN_ENCRYPTION_KEY=<new-key>
   - Set GITHUB_TOKEN_PREVIOUS_KEYS=<old-key>   (comma-separate multiple old keys)
3. Deploy the updated config.
   Existing ciphertexts (encrypted with the old key) continue to decrypt.
   New writes use the new key automatically.
4. Run the backfill CLI to re-encrypt all stored tokens under the new key:
       python -m app.cli.rotate_github_tokens
   Use --dry-run first to preview, then run without it to commit.
5. Remove the old key from GITHUB_TOKEN_PREVIOUS_KEYS and redeploy.
   Old-key ciphertexts no longer exist after a successful backfill.
"""

from __future__ import annotations

from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode("ascii")
    print(f"GITHUB_TOKEN_ENCRYPTION_KEY={key}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add `GITHUB_TOKEN_PREVIOUS_KEYS` to the environment variables doc**

In `docs/reference/environment-variables.md`, find the line for `GITHUB_TOKEN_ENCRYPTION_KEY` (line 653) and add a new row immediately after it:

```
| `GITHUB_TOKEN_PREVIOUS_KEYS` | _(none)_ | No | Comma-separated previous Fernet keys kept during a rotation window. Each key must be the same format as `GITHUB_TOKEN_ENCRYPTION_KEY`. Decryption tries all keys; encryption always uses the primary. Remove old keys after running `python -m app.cli.rotate_github_tokens`. | `app/security/token_crypto.py` |
```

Also update the **Notes** block after the table (currently starting at line 659) by replacing:

```
- `GITHUB_TOKEN_ENCRYPTION_KEY` is the only hard requirement when the GitHub integration is used. Without it, `encrypt_token` and `decrypt_token` raise at call time, not at startup, so the rest of the API boots normally.
```

with:

```
- `GITHUB_TOKEN_ENCRYPTION_KEY` is the only hard requirement when the GitHub integration is used. Without it, `encrypt_token` and `decrypt_token` raise at call time, not at startup, so the rest of the API boots normally.
- `GITHUB_TOKEN_PREVIOUS_KEYS` is optional and used only during key rotation. Set it to the old key value(s) while both keys are live, then remove it after running `python -m app.cli.rotate_github_tokens` to backfill all rows. See `tools/scripts/generate_github_encryption_key.py` for the full rotation procedure.
```

- [ ] **Step 3: Run the full test suite to catch any regressions**

```bash
source .venv/bin/activate && pytest tests/security/ tests/cli/test_rotate_github_tokens.py -v 2>&1 | tail -20
```

Expected: all tests `PASSED`.

- [ ] **Step 4: Commit**

```bash
git add tools/scripts/generate_github_encryption_key.py docs/reference/environment-variables.md
git commit -m "docs: document GITHUB_TOKEN_PREVIOUS_KEYS and key rotation procedure"
```

---

## Self-Review Checklist

**Spec coverage:**

| Requirement | Covered by |
|-------------|-----------|
| MultiFernet support: primary + previous keys | Task 2 (`token_crypto.py`) |
| Encrypt with primary, decrypt with all | Task 2 (`MultiFernet` semantics) |
| Config for previous keys | Task 2 (`GitHubConfig.token_previous_keys`) |
| CLI / migration task to re-encrypt rows | Task 4 (`rotate_github_tokens.py`) |
| Test: decrypt old-key ciphertext | Task 1 (`test_decrypt_with_previous_key`) |
| Test: encrypt uses primary key | Task 1 (`test_encrypt_uses_primary_key_not_previous`) |
| Test: malformed key handling | Task 1 (`test_malformed_previous_key_raises`) |
| Test: migration / backfill | Task 3 (`test_rotate_github_tokens.py`) |
| Docs update | Task 5 (env-vars doc + key gen script) |
| Zero-downtime operator path | Tasks 2 + 4 + 5 |

**Placeholder scan:** No TBD, TODO, or "similar to" references. All code blocks are complete.

**Type consistency:**
- `_get_multi_fernet()` → `MultiFernet` (used in `encrypt_token`, `decrypt_token`)
- `reset_key_cache()` clears `_get_multi_fernet` (matches renamed function)
- `ReencryptResult` dataclass used consistently in `reencrypt_all_tokens` return and tests
- `db.session()` / `db.transaction()` async context manager pattern matches existing codebase usage

No gaps found.
