# Backup Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encrypt backup archives at rest with Fernet and enforce strict restore safety limits (upload cap, zip bomb / path-traversal rejection) before any extraction or DB write.

**Architecture:** A new `BackupConfig` pydantic model wires encryption and safety limits into `AppConfig`. A thin `backup_crypto.py` handles Fernet encrypt/decrypt; `backup_safety.py` validates ZIP central-directory metadata without decompressing any entry. `backup_archive_service.py` uses both during create (encrypt before write) and restore (decrypt + validate before DB access). The restore router endpoint streams uploads in chunks and aborts at a configurable byte cap.

**Tech Stack:** Python 3.13, `cryptography.fernet.Fernet` (already installed), `zipfile` (stdlib), Pydantic v2, FastAPI.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/config/backup.py` | **Create** | `BackupConfig` model + `load_backup_config()` |
| `app/config/settings.py` | **Modify** | Import and wire `BackupConfig` into `AppConfig` |
| `app/infrastructure/persistence/backup_crypto.py` | **Create** | `encrypt_backup`, `decrypt_backup`, `is_fernet_ciphertext` |
| `app/infrastructure/persistence/backup_safety.py` | **Create** | `validate_zip_safety`, `ZipSafetyViolation` |
| `app/infrastructure/persistence/backup_archive_service.py` | **Modify** | Encrypt on create; decrypt + validate on restore |
| `app/api/routers/backups.py` | **Modify** | Capped stream-read for restore; correct content-type for download |
| `tests/test_backup_hardening.py` | **Create** | All hardening unit tests |
| `docs/guides/backup-and-restore.md` | **Modify** | Backup Encryption section |

---

## Task 1: BackupConfig

**Files:**
- Create: `app/config/backup.py`
- Modify: `app/config/settings.py` (lines 40–41 for import, line 251 for field)
- Test: `tests/test_backup_hardening.py` (new file, first batch of tests)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_backup_hardening.py
"""Unit tests for backup hardening: config, crypto, safety, restore pipeline."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# BackupConfig
# ---------------------------------------------------------------------------

class TestBackupConfig:
    def test_encryption_enabled_when_key_set(self) -> None:
        from app.config.backup import BackupConfig

        cfg = BackupConfig(encryption_key="placeholder_will_be_replaced")
        assert cfg.is_encryption_enabled is True

    def test_encryption_not_enabled_without_key(self) -> None:
        from app.config.backup import BackupConfig

        cfg = BackupConfig()
        assert cfg.is_encryption_enabled is False

    def test_explicit_false_overrides_key(self) -> None:
        from app.config.backup import BackupConfig

        cfg = BackupConfig(encryption_key="placeholder_will_be_replaced", encryption_enabled=False)
        assert cfg.is_encryption_enabled is False

    def test_explicit_true_without_key_raises(self) -> None:
        from app.config.backup import BackupConfig

        with pytest.raises(ValidationError, match="BACKUP_ENCRYPTION_ENABLED"):
            BackupConfig(encryption_enabled=True)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestBackupConfig -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `app.config.backup` does not exist yet.

- [ ] **Step 3: Create `app/config/backup.py`**

```python
"""Backup encryption and safety-limit configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class BackupConfig(BaseModel):
    """Encryption key, feature flag, and ZIP safety limits for the backup subsystem."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    encryption_key: SecretStr | None = Field(
        default=None,
        validation_alias="BACKUP_ENCRYPTION_KEY",
        description=(
            "Fernet key (44-char url-safe base64). "
            "Generate with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ),
    )
    encryption_enabled: bool | None = Field(
        default=None,
        validation_alias="BACKUP_ENCRYPTION_ENABLED",
        description=(
            "Explicit on/off override. Omit to auto-derive: "
            "True when encryption_key is set, False otherwise."
        ),
    )

    max_restore_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        validation_alias="BACKUP_MAX_RESTORE_BYTES",
        description="Maximum upload size in bytes for the restore endpoint (default 100 MB).",
    )
    max_zip_entries: int = Field(
        default=100,
        ge=1,
        validation_alias="BACKUP_MAX_ZIP_ENTRIES",
        description="Maximum number of entries allowed in a restore archive.",
    )
    max_compressed_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
        validation_alias="BACKUP_MAX_COMPRESSED_BYTES",
        description="Maximum total compressed size of all ZIP entries (default 100 MB).",
    )
    max_decompressed_bytes: int = Field(
        default=500 * 1024 * 1024,
        ge=1,
        validation_alias="BACKUP_MAX_DECOMPRESSED_BYTES",
        description="Maximum total uncompressed size of all ZIP entries (default 500 MB).",
    )
    max_compression_ratio: float = Field(
        default=100.0,
        ge=1.0,
        validation_alias="BACKUP_MAX_COMPRESSION_RATIO",
        description="Maximum per-entry compression ratio — zip bomb guard (default 100).",
    )

    @model_validator(mode="after")
    def _key_required_when_explicitly_enabled(self) -> "BackupConfig":
        if self.encryption_enabled is True and self.encryption_key is None:
            raise ValueError(
                "BACKUP_ENCRYPTION_ENABLED=true requires BACKUP_ENCRYPTION_KEY to be set."
            )
        return self

    @property
    def is_encryption_enabled(self) -> bool:
        """True if backups should be encrypted.

        Auto-derives from key presence when BACKUP_ENCRYPTION_ENABLED is unset.
        """
        if self.encryption_enabled is not None:
            return self.encryption_enabled
        return self.encryption_key is not None


def load_backup_config() -> BackupConfig:
    """Return BackupConfig from the current application settings (lazy, cached via load_config)."""
    from app.config.settings import load_config

    return load_config(allow_stub_telegram=True).backup
```

- [ ] **Step 4: Wire `BackupConfig` into `AppConfig` in `app/config/settings.py`**

Add import after line 40 (`from .retention import RetentionConfig`):
```python
from .backup import BackupConfig
```

Add field after line 251 (`retention: RetentionConfig = Field(default_factory=RetentionConfig)`):
```python
    backup: BackupConfig = Field(default_factory=BackupConfig)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestBackupConfig -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/config/backup.py app/config/settings.py tests/test_backup_hardening.py
git commit -m "feat(config): add BackupConfig for encryption and safety limits"
```

---

## Task 2: Backup Crypto

**Files:**
- Create: `app/infrastructure/persistence/backup_crypto.py`
- Modify: `tests/test_backup_hardening.py` (add `TestBackupCrypto` class)

- [ ] **Step 1: Add failing tests to `tests/test_backup_hardening.py`**

Append after the `TestBackupConfig` class:

```python
# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

from cryptography.fernet import Fernet as _Fernet

_TEST_KEY = _Fernet.generate_key()          # bytes, valid Fernet key
_TEST_KEY_STR = _TEST_KEY.decode()          # str version
_OTHER_KEY = _Fernet.generate_key().decode()  # different key for wrong-key tests


class TestBackupCrypto:
    def test_roundtrip(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_crypto import (
            decrypt_backup,
            encrypt_backup,
        )

        plaintext = b"hello backup world"
        ciphertext = encrypt_backup(plaintext, SecretStr(_TEST_KEY_STR))
        assert decrypt_backup(ciphertext, SecretStr(_TEST_KEY_STR)) == plaintext

    def test_wrong_key_raises(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_crypto import (
            InvalidBackupCiphertextError,
            decrypt_backup,
            encrypt_backup,
        )

        ciphertext = encrypt_backup(b"data", SecretStr(_TEST_KEY_STR))
        with pytest.raises(InvalidBackupCiphertextError):
            decrypt_backup(ciphertext, SecretStr(_OTHER_KEY))

    def test_is_fernet_ciphertext_true(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_crypto import (
            encrypt_backup,
            is_fernet_ciphertext,
        )

        ciphertext = encrypt_backup(b"data", SecretStr(_TEST_KEY_STR))
        assert is_fernet_ciphertext(ciphertext) is True

    def test_is_fernet_ciphertext_false_for_raw_zip(self) -> None:
        from app.infrastructure.persistence.backup_crypto import is_fernet_ciphertext

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        assert is_fernet_ciphertext(buf.getvalue()) is False
```

- [ ] **Step 2: Run to verify tests fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestBackupCrypto -v
```

Expected: `ImportError` — `backup_crypto` does not exist yet.

- [ ] **Step 3: Create `app/infrastructure/persistence/backup_crypto.py`**

```python
"""Fernet encryption/decryption for backup archives at rest."""

from __future__ import annotations

from pydantic import SecretStr

__all__ = [
    "FERNET_MAGIC",
    "InvalidBackupCiphertextError",
    "MissingBackupEncryptionKeyError",
    "decrypt_backup",
    "encrypt_backup",
    "is_fernet_ciphertext",
]

FERNET_MAGIC = b"gAAAAA"


class InvalidBackupCiphertextError(ValueError):
    """Raised when a backup ciphertext cannot be decrypted (wrong key or corruption)."""


class MissingBackupEncryptionKeyError(RuntimeError):
    """Raised when encryption is requested but BACKUP_ENCRYPTION_KEY is not configured."""


def _fernet(key: SecretStr) -> "cryptography.fernet.Fernet":  # type: ignore[name-defined]
    from cryptography.fernet import Fernet

    raw = key.get_secret_value()
    raw_bytes = raw.encode() if isinstance(raw, str) else raw
    return Fernet(raw_bytes)


def is_fernet_ciphertext(data: bytes) -> bool:
    """Return True if *data* starts with the Fernet token prefix."""
    return data[:6] == FERNET_MAGIC


def encrypt_backup(zip_bytes: bytes, key: SecretStr) -> bytes:
    """Fernet-encrypt *zip_bytes* and return opaque ciphertext bytes."""
    return _fernet(key).encrypt(zip_bytes)


def decrypt_backup(data: bytes, key: SecretStr) -> bytes:
    """Decrypt Fernet *data* and return raw ZIP bytes.

    Raises InvalidBackupCiphertextError on wrong key or corrupted ciphertext.
    """
    from cryptography.fernet import InvalidToken

    try:
        return _fernet(key).decrypt(data)
    except InvalidToken as exc:
        raise InvalidBackupCiphertextError(
            "Could not decrypt backup archive (wrong key or corrupted ciphertext)"
        ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestBackupCrypto -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/persistence/backup_crypto.py tests/test_backup_hardening.py
git commit -m "feat(backup): add Fernet encrypt/decrypt helpers"
```

---

## Task 3: ZIP Safety Validator

**Files:**
- Create: `app/infrastructure/persistence/backup_safety.py`
- Modify: `tests/test_backup_hardening.py` (add `TestZipSafety` class)

- [ ] **Step 1: Add failing tests to `tests/test_backup_hardening.py`**

Append after `TestBackupCrypto`:

```python
# ---------------------------------------------------------------------------
# ZIP safety
# ---------------------------------------------------------------------------

_LIMITS = dict(
    max_entries=10,
    max_compressed_bytes=10 * 1024 * 1024,
    max_decompressed_bytes=1000,
    max_ratio=50.0,
)


def _one_entry_zip(filename: str = "file.txt", content: bytes = b"hello") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, content)
    return buf.getvalue()


class TestZipSafety:
    def test_valid_archive_passes(self) -> None:
        from app.infrastructure.persistence.backup_safety import validate_zip_safety

        validate_zip_safety(_one_entry_zip(), **_LIMITS)  # should not raise

    def test_empty_archive_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            pass
        with pytest.raises(ZipSafetyViolation, match="no entries"):
            validate_zip_safety(buf.getvalue(), **_LIMITS)

    def test_too_many_entries_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(11):
                zf.writestr(f"f{i}.txt", "x")
        with pytest.raises(ZipSafetyViolation, match="entries"):
            validate_zip_safety(buf.getvalue(), **_LIMITS)

    def test_oversized_decompressed_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        # 1001 bytes > max_decompressed_bytes=1000
        with pytest.raises(ZipSafetyViolation, match="decompressed"):
            validate_zip_safety(_one_entry_zip(content=b"x" * 1001), **_LIMITS)

    def test_zip_bomb_ratio_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        # "a" * 5000 with DEFLATE compresses to ~15 bytes → ratio ≈ 333 > max_ratio=50
        limits = {**_LIMITS, "max_decompressed_bytes": 10 * 1024 * 1024}
        with pytest.raises(ZipSafetyViolation, match="ratio"):
            validate_zip_safety(_one_entry_zip(content=b"a" * 5000), **limits)

    def test_path_traversal_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        with pytest.raises(ZipSafetyViolation, match="traversal"):
            validate_zip_safety(_one_entry_zip(filename="../../evil.txt"), **_LIMITS)

    def test_absolute_path_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        with pytest.raises(ZipSafetyViolation, match="absolute"):
            validate_zip_safety(_one_entry_zip(filename="/etc/passwd"), **_LIMITS)

    def test_corrupt_zip_raises_violation(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        with pytest.raises(ZipSafetyViolation, match="corrupt"):
            validate_zip_safety(b"not a zip", **_LIMITS)
```

- [ ] **Step 2: Run to verify tests fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestZipSafety -v
```

Expected: `ImportError` — `backup_safety` does not exist yet.

- [ ] **Step 3: Create `app/infrastructure/persistence/backup_safety.py`**

```python
"""ZIP archive safety validation — central-directory only, no decompression."""

from __future__ import annotations

import zipfile
from io import BytesIO

__all__ = ["ZipSafetyViolation", "validate_zip_safety"]


class ZipSafetyViolation(ValueError):
    """Raised when a ZIP archive fails a safety check."""


def validate_zip_safety(
    data: bytes,
    *,
    max_entries: int,
    max_compressed_bytes: int,
    max_decompressed_bytes: int,
    max_ratio: float,
) -> None:
    """Validate *data* as a safe ZIP archive using central-directory metadata only.

    No entry content is decompressed during validation.

    Raises ZipSafetyViolation with a descriptive message if any check fails.
    Raises ZipSafetyViolation (wrapping BadZipFile) for corrupt/invalid archives.
    """
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as zf:
            entries = zf.infolist()
    except zipfile.BadZipFile as exc:
        raise ZipSafetyViolation(f"Invalid or corrupt ZIP archive: {exc}") from exc

    if not entries:
        raise ZipSafetyViolation("Archive contains no entries")

    if len(entries) > max_entries:
        raise ZipSafetyViolation(
            f"Archive has {len(entries)} entries; limit is {max_entries}"
        )

    total_compressed = sum(e.compress_size for e in entries)
    if total_compressed > max_compressed_bytes:
        raise ZipSafetyViolation(
            f"Total compressed size {total_compressed} B exceeds limit {max_compressed_bytes} B"
        )

    total_decompressed = sum(e.file_size for e in entries)
    if total_decompressed > max_decompressed_bytes:
        raise ZipSafetyViolation(
            f"Total decompressed size {total_decompressed} B exceeds limit "
            f"{max_decompressed_bytes} B"
        )

    for entry in entries:
        ratio = entry.file_size / max(entry.compress_size, 1)
        if ratio > max_ratio:
            raise ZipSafetyViolation(
                f"Entry '{entry.filename}' compression ratio {ratio:.1f} exceeds "
                f"limit {max_ratio} (zip bomb guard)"
            )

        name = entry.filename
        if name.startswith("/"):
            raise ZipSafetyViolation(
                f"Entry '{name}' has an absolute path (path traversal risk)"
            )
        parts = name.replace("\\", "/").split("/")
        if ".." in parts:
            raise ZipSafetyViolation(
                f"Entry '{name}' contains '..' component (path traversal risk)"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestZipSafety -v
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/persistence/backup_safety.py tests/test_backup_hardening.py
git commit -m "feat(backup): add ZIP safety validator (zip bomb + path traversal)"
```

---

## Task 4: Wire Encryption into Backup Creation

**Files:**
- Modify: `app/infrastructure/persistence/backup_archive_service.py`

The current create path writes directly to `zip_path` with `zipfile.ZipFile(zip_path, "w", ...)`. This task changes it to build the ZIP into a `BytesIO` buffer first, then optionally encrypt, then write to disk.

- [ ] **Step 1: Add imports and update `async_create_backup_archive` signature**

At the top of `backup_archive_service.py`, add imports after the existing `zipfile` import:

```python
from app.config.backup import BackupConfig, load_backup_config
from app.infrastructure.persistence.backup_crypto import encrypt_backup
```

Change the `async_create_backup_archive` signature from:
```python
async def async_create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
) -> None:
```
to:
```python
async def async_create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
    cfg: BackupConfig | None = None,
) -> None:
```

- [ ] **Step 2: Replace the `zipfile.ZipFile(zip_path, ...)` block**

Find (starting around line 213):
```python
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        zip_path = backup_dir / f"ratatoskr-backup-{user_id}-{timestamp}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, default=str, indent=2))
            archive.writestr("requests.json", json.dumps(requests_data, default=str))
            archive.writestr("summaries.json", json.dumps(summaries_data, default=str))
            archive.writestr("tags.json", json.dumps(tags_data, default=str))
            archive.writestr("summary_tags.json", json.dumps(summary_tags_data, default=str))
            archive.writestr("collections.json", json.dumps(collections_data, default=str))
            archive.writestr(
                "collection_items.json", json.dumps(collection_items_data, default=str)
            )
            archive.writestr("highlights.json", json.dumps(highlights_data, default=str))
            archive.writestr(
                "preferences.json",
                json.dumps(preferences, default=str) if preferences else "{}",
            )

        file_size = zip_path.stat().st_size
```

Replace with:

```python
        _cfg = cfg or load_backup_config()
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, default=str, indent=2))
            archive.writestr("requests.json", json.dumps(requests_data, default=str))
            archive.writestr("summaries.json", json.dumps(summaries_data, default=str))
            archive.writestr("tags.json", json.dumps(tags_data, default=str))
            archive.writestr("summary_tags.json", json.dumps(summary_tags_data, default=str))
            archive.writestr("collections.json", json.dumps(collections_data, default=str))
            archive.writestr(
                "collection_items.json", json.dumps(collection_items_data, default=str)
            )
            archive.writestr("highlights.json", json.dumps(highlights_data, default=str))
            archive.writestr(
                "preferences.json",
                json.dumps(preferences, default=str) if preferences else "{}",
            )

        zip_bytes = buf.getvalue()
        if _cfg.is_encryption_enabled and _cfg.encryption_key is not None:
            payload = encrypt_backup(zip_bytes, _cfg.encryption_key)
            suffix = ".zip.enc"
        else:
            payload = zip_bytes
            suffix = ".zip"

        zip_path = backup_dir / f"ratatoskr-backup-{user_id}-{timestamp}{suffix}"
        zip_path.write_bytes(payload)
        file_size = zip_path.stat().st_size
```

- [ ] **Step 3: Update the sync wrapper to pass `cfg`**

Find `create_backup_archive` (sync wrapper) and change:
```python
def create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
) -> None:
    """Synchronous compatibility wrapper for backup archive creation."""
    asyncio.run(
        async_create_backup_archive(
            user_id=user_id,
            backup_id=backup_id,
            db=db,
            data_dir=data_dir,
        )
    )
```
to:
```python
def create_backup_archive(
    user_id: int,
    backup_id: int,
    *,
    db: Database | None = None,
    data_dir: str | None = None,
    cfg: BackupConfig | None = None,
) -> None:
    """Synchronous compatibility wrapper for backup archive creation."""
    asyncio.run(
        async_create_backup_archive(
            user_id=user_id,
            backup_id=backup_id,
            db=db,
            data_dir=data_dir,
            cfg=cfg,
        )
    )
```

- [ ] **Step 4: Run existing backup tests to confirm no regressions**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_service.py -v
```

Expected: all existing tests PASS (they don't touch the create path).

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure/persistence/backup_archive_service.py
git commit -m "feat(backup): encrypt archive on write when BACKUP_ENCRYPTION_KEY is set"
```

---

## Task 5: Wire Decrypt + Safety into Restore

**Files:**
- Modify: `app/infrastructure/persistence/backup_archive_service.py`
- Modify: `tests/test_backup_hardening.py` (add `TestRestoreHardening` class)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_backup_hardening.py`:

```python
# ---------------------------------------------------------------------------
# Restore pipeline hardening (no DB — uses version-check early exit)
# ---------------------------------------------------------------------------

def _make_valid_zip(version: str = "1.0") -> bytes:
    """Minimal backup ZIP with all required files."""
    manifest = {
        "version": version,
        "user_id": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "counts": {
            "requests": 0, "summaries": 0, "tags": 0, "summary_tags": 0,
            "collections": 0, "collection_items": 0, "highlights": 0,
        },
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name in ["requests", "summaries", "tags", "summary_tags",
                     "collections", "collection_items", "highlights"]:
            zf.writestr(f"{name}.json", "[]")
        zf.writestr("preferences.json", "{}")
    return buf.getvalue()


class TestRestoreHardening:
    """Restore pipeline: decrypt + safety validation before DB access.

    Uses version="99.0" so restore returns early (no DB) after decryption + safety pass.
    """

    def test_restore_accepts_encrypted_archive(self) -> None:
        """Encrypted archive is decrypted and parsed; error is version mismatch, not decrypt."""
        from pydantic import SecretStr

        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        zip_bytes = _make_valid_zip(version="99.0")
        encrypted = encrypt_backup(zip_bytes, SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig(encryption_key=_TEST_KEY_STR)

        result = restore_from_archive(user_id=1, zip_bytes=encrypted, cfg=cfg)
        assert len(result["errors"]) == 1
        assert "Unsupported backup version" in result["errors"][0]

    def test_restore_accepts_unencrypted_archive(self) -> None:
        """Plaintext ZIP accepted when no key is configured (auto-detect)."""
        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )

        zip_bytes = _make_valid_zip(version="99.0")
        cfg = BackupConfig()  # no key

        result = restore_from_archive(user_id=1, zip_bytes=zip_bytes, cfg=cfg)
        assert len(result["errors"]) == 1
        assert "Unsupported backup version" in result["errors"][0]

    def test_restore_no_key_for_encrypted_archive_returns_error(self) -> None:
        """Encrypted bytes with no key configured → descriptive error, no crash."""
        from pydantic import SecretStr

        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        zip_bytes = _make_valid_zip()
        encrypted = encrypt_backup(zip_bytes, SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig()  # no key

        result = restore_from_archive(user_id=1, zip_bytes=encrypted, cfg=cfg)
        assert any("BACKUP_ENCRYPTION_KEY" in e for e in result["errors"])

    def test_restore_wrong_key_returns_error(self) -> None:
        """Encrypted bytes with wrong key → descriptive error, no crash."""
        from pydantic import SecretStr

        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        zip_bytes = _make_valid_zip()
        encrypted = encrypt_backup(zip_bytes, SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig(encryption_key=_OTHER_KEY)

        result = restore_from_archive(user_id=1, zip_bytes=encrypted, cfg=cfg)
        assert any("decrypt" in e.lower() for e in result["errors"])

    def test_restore_zip_bomb_rejected_before_db(self) -> None:
        """Safety check rejects zip bomb before any DB access."""
        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("bomb.txt", b"a" * 5000)

        cfg = BackupConfig(
            max_zip_entries=100,
            max_compressed_bytes=10 * 1024 * 1024,
            max_decompressed_bytes=10 * 1024 * 1024,
            max_compression_ratio=50.0,  # 5000/~15 ≈ 333 > 50
        )
        result = restore_from_archive(user_id=1, zip_bytes=buf.getvalue(), cfg=cfg)
        assert any("ratio" in e.lower() for e in result["errors"])

    def test_restore_path_traversal_rejected_before_db(self) -> None:
        """Safety check rejects path-traversal entry before any DB access."""
        from app.config.backup import BackupConfig
        from app.infrastructure.persistence.backup_archive_service import (
            restore_from_archive,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../evil.txt", "evil")

        cfg = BackupConfig()
        result = restore_from_archive(user_id=1, zip_bytes=buf.getvalue(), cfg=cfg)
        assert any("traversal" in e.lower() for e in result["errors"])
```

- [ ] **Step 2: Run to verify tests fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestRestoreHardening -v
```

Expected: `TypeError` — `restore_from_archive` does not accept `cfg` yet.

- [ ] **Step 3: Update imports in `backup_archive_service.py`**

Replace the existing import block for backup_crypto/backup_safety imports (they don't exist yet — add them after the `zipfile` import line):

```python
from app.config.backup import BackupConfig, load_backup_config
from app.infrastructure.persistence.backup_crypto import (
    InvalidBackupCiphertextError,
    decrypt_backup,
    encrypt_backup,
    is_fernet_ciphertext,
)
from app.infrastructure.persistence.backup_safety import ZipSafetyViolation, validate_zip_safety
```

Note: the `encrypt_backup` import was added in Task 4; consolidate all three imports into one block now. Remove the `from app.config.backup import BackupConfig, load_backup_config` and `from app.infrastructure.persistence.backup_crypto import encrypt_backup` lines added in Task 4 and replace with the block above.

- [ ] **Step 4: Update `async_restore_from_archive` signature**

Change:
```python
async def async_restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
) -> dict[str, Any]:
```
to:
```python
async def async_restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
    cfg: BackupConfig | None = None,
) -> dict[str, Any]:
```

- [ ] **Step 5: Add decrypt + safety logic at the start of `async_restore_from_archive`**

The current function body begins with:
```python
    restored: dict[str, int] = {
```

Insert the following block immediately after the function signature's docstring and before `restored = ...`:

```python
    _cfg = cfg or load_backup_config()
    errors: list[str] = []
    restored: dict[str, int] = {
        "requests": 0,
        "summaries": 0,
        "tags": 0,
        "summary_tags": 0,
        "collections": 0,
        "collection_items": 0,
        "highlights": 0,
    }
    skipped: dict[str, int] = {
        "requests": 0,
        "summaries": 0,
        "tags": 0,
        "collections": 0,
    }

    # --- Decrypt ---
    if is_fernet_ciphertext(zip_bytes):
        if _cfg.encryption_key is None:
            return {
                "restored": restored,
                "skipped": skipped,
                "errors": [
                    "Encrypted backup received but BACKUP_ENCRYPTION_KEY is not configured. "
                    "Set the key that was active when this backup was created."
                ],
            }
        try:
            zip_bytes = decrypt_backup(zip_bytes, _cfg.encryption_key)
        except InvalidBackupCiphertextError as exc:
            return {
                "restored": restored,
                "skipped": skipped,
                "errors": [f"Could not decrypt backup archive: {exc}"],
            }
    else:
        logger.warning("restore_unencrypted_backup", extra={"user_id": user_id})

    # --- ZIP safety ---
    try:
        validate_zip_safety(
            zip_bytes,
            max_entries=_cfg.max_zip_entries,
            max_compressed_bytes=_cfg.max_compressed_bytes,
            max_decompressed_bytes=_cfg.max_decompressed_bytes,
            max_ratio=_cfg.max_compression_ratio,
        )
    except ZipSafetyViolation as exc:
        return {
            "restored": restored,
            "skipped": skipped,
            "errors": [f"Unsafe archive rejected: {exc}"],
        }
```

Then **remove** the duplicate `restored`, `skipped`, and `errors` initializations from the original function body (they appear right after this inserted block).

- [ ] **Step 6: Update sync wrapper `restore_from_archive` to accept `cfg`**

Change:
```python
def restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
) -> dict[str, Any]:
    """Synchronous compatibility wrapper for backup archive restore."""
    return asyncio.run(async_restore_from_archive(user_id=user_id, zip_bytes=zip_bytes, db=db))
```
to:
```python
def restore_from_archive(
    user_id: int,
    zip_bytes: bytes,
    *,
    db: Database | None = None,
    cfg: BackupConfig | None = None,
) -> dict[str, Any]:
    """Synchronous compatibility wrapper for backup archive restore."""
    return asyncio.run(
        async_restore_from_archive(user_id=user_id, zip_bytes=zip_bytes, db=db, cfg=cfg)
    )
```

- [ ] **Step 7: Run all backup tests**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py tests/test_backup_service.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app/infrastructure/persistence/backup_archive_service.py tests/test_backup_hardening.py
git commit -m "feat(backup): decrypt + validate ZIP safety before restore DB access"
```

---

## Task 6: Router Hardening

**Files:**
- Modify: `app/api/routers/backups.py`
- Modify: `tests/test_backup_hardening.py` (add `TestUploadCap` class)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_backup_hardening.py`:

```python
# ---------------------------------------------------------------------------
# Upload cap helper
# ---------------------------------------------------------------------------

class TestUploadCap:
    def test_within_limit_returns_bytes(self) -> None:
        import asyncio

        from app.api.routers.backups import _read_upload_capped

        class _Fake:
            def __init__(self, data: bytes) -> None:
                self._buf = io.BytesIO(data)

            async def read(self, n: int = -1) -> bytes:
                return self._buf.read(n)

        result = asyncio.run(_read_upload_capped(_Fake(b"hello"), limit=100))
        assert result == b"hello"

    def test_over_limit_raises_api_exception(self) -> None:
        import asyncio

        from app.api.exceptions import APIException
        from app.api.routers.backups import _read_upload_capped

        class _Fake:
            def __init__(self, data: bytes) -> None:
                self._buf = io.BytesIO(data)

            async def read(self, n: int = -1) -> bytes:
                return self._buf.read(n)

        with pytest.raises(APIException) as exc_info:
            asyncio.run(_read_upload_capped(_Fake(b"x" * 11), limit=10))
        assert exc_info.value.status_code == 413

    def test_empty_returns_empty_bytes(self) -> None:
        import asyncio

        from app.api.routers.backups import _read_upload_capped

        class _Fake:
            async def read(self, n: int = -1) -> bytes:
                return b""

        result = asyncio.run(_read_upload_capped(_Fake(), limit=100))
        assert result == b""
```

- [ ] **Step 2: Run to verify tests fail**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py::TestUploadCap -v
```

Expected: `ImportError` — `_read_upload_capped` is not in the router yet.

- [ ] **Step 3: Update `app/api/routers/backups.py`**

**Add imports** at the top, after the existing imports:

```python
from app.config.backup import load_backup_config
from app.infrastructure.persistence.backup_archive_service import (
    async_create_backup_archive,
    async_restore_from_archive,
)
```

(The `async_restore_from_archive` import already exists — check and deduplicate.)

**Add the `_read_upload_capped` helper** before the first route:

```python
_CHUNK_SIZE = 1024 * 1024  # 1 MB


async def _read_upload_capped(file: Any, limit: int) -> bytes:
    """Read *file* in chunks, raising APIException(413) if total exceeds *limit*."""
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        received += len(chunk)
        if received > limit:
            raise APIException(
                message=f"Upload exceeds maximum allowed size "
                f"({limit // (1024 * 1024)} MB)",
                error_code=ErrorCode.VALIDATION_ERROR,
                status_code=413,
            )
        chunks.append(chunk)
    return b"".join(chunks)
```

**Replace the `restore_backup` endpoint**:

```python
@router.post("/restore")
async def restore_backup(
    file: UploadFile,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore user data from an uploaded backup archive (ZIP or encrypted .zip.enc)."""
    cfg = load_backup_config()
    content = await _read_upload_capped(file, cfg.max_restore_bytes)
    if not content:
        raise APIException(
            message="Uploaded file is empty",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )
    summary = await async_restore_from_archive(
        user["user_id"], content, db=get_session_manager(), cfg=cfg
    )
    return success_response(summary)
```

**Update `create_backup` background task** to pass cfg:

```python
    background_tasks.add_task(
        async_create_backup_archive,
        user_id=user_id,
        backup_id=backup["id"],
        db=get_session_manager(),
        cfg=load_backup_config(),
    )
```

**Update `download_backup`** to set the correct content-type based on actual file format:

Replace:
```python
    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/zip",
    )
```
with:
```python
    filename = os.path.basename(file_path)
    media_type = "application/zip" if filename.endswith(".zip") else "application/octet-stream"
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
    )
```

- [ ] **Step 4: Run all hardening tests**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_hardening.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full backup test suite**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_service.py tests/test_backup_hardening.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run type check**

```bash
source .venv/bin/activate && make type 2>&1 | grep -E "backup|error" | head -20
```

Fix any mypy errors before committing.

- [ ] **Step 7: Commit**

```bash
git add app/api/routers/backups.py tests/test_backup_hardening.py
git commit -m "feat(backup): cap restore upload size; correct download content-type"
```

---

## Task 7: Docs Update

**Files:**
- Modify: `docs/guides/backup-and-restore.md`

- [ ] **Step 1: Add Backup Encryption section**

In `docs/guides/backup-and-restore.md`, insert the following section between "Config And Secrets" and "Verify The Backup":

```markdown
### Backup Encryption

User export archives (`data/backups/<user_id>/`) are encrypted at rest when
`BACKUP_ENCRYPTION_KEY` is set. Without a key, archives are stored as
unencrypted `.zip` files (original behavior).

**Generate a key:**

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add it to `.env`:

```bash
BACKUP_ENCRYPTION_KEY=<output from above>
```

Once set, new backups are written as `.zip.enc` files (Fernet-encrypted ZIP).
The download endpoint serves the encrypted bytes directly. Restore accepts both
`.zip.enc` (decrypts automatically) and legacy `.zip` archives, so existing
backups remain restorable after adding a key.

**Warning:** Losing `BACKUP_ENCRYPTION_KEY` makes encrypted backups permanently
unrecoverable. Store the key outside the host in a secrets manager, password
manager, or offline vault.

**Disable encryption explicitly** (e.g., for a development instance where a key
is set in shared config but encryption is not wanted locally):

```bash
BACKUP_ENCRYPTION_ENABLED=false
```

**Manually decrypt a `.zip.enc` file** (for offline inspection):

```python
from cryptography.fernet import Fernet
key = b"<your BACKUP_ENCRYPTION_KEY>"
data = open("ratatoskr-backup-1-20260515_120000.zip.enc", "rb").read()
zip_bytes = Fernet(key).decrypt(data)
open("backup.zip", "wb").write(zip_bytes)
```

**Restore safety limits** (all configurable via env vars):

| Variable | Default | Purpose |
|---|---|---|
| `BACKUP_MAX_RESTORE_BYTES` | 104857600 (100 MB) | Upload size gate |
| `BACKUP_MAX_ZIP_ENTRIES` | 100 | Max entries in archive |
| `BACKUP_MAX_COMPRESSED_BYTES` | 104857600 (100 MB) | Max total compressed size |
| `BACKUP_MAX_DECOMPRESSED_BYTES` | 524288000 (500 MB) | Max total decompressed size |
| `BACKUP_MAX_COMPRESSION_RATIO` | 100.0 | Per-entry ratio cap (zip bomb guard) |
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
source .venv/bin/activate && python -m pytest tests/test_backup_service.py tests/test_backup_hardening.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/guides/backup-and-restore.md
git commit -m "docs(backup): document encryption setup and restore safety limits"
```

---

## Acceptance Checklist

- [ ] `BACKUP_ENCRYPTION_KEY` set → new backups written as `.zip.enc`; download serves `application/octet-stream`
- [ ] No key set → new backups written as `.zip`; existing behavior preserved
- [ ] `BACKUP_ENCRYPTION_ENABLED=false` with key → unencrypted write
- [ ] Restore auto-detects encrypted vs plaintext input
- [ ] Restore rejects zip bombs, oversized archives, path traversal, and too many entries before any DB write
- [ ] Restore upload capped at `BACKUP_MAX_RESTORE_BYTES` with HTTP 413
- [ ] All tests in `tests/test_backup_hardening.py` pass
- [ ] All tests in `tests/test_backup_service.py` pass
