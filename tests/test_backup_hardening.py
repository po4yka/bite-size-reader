"""Unit tests for backup hardening: config, crypto, safety, restore pipeline."""

from __future__ import annotations

import io
import json
import zipfile
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app.config.backup import BackupConfig


# ---------------------------------------------------------------------------
# BackupConfig
# ---------------------------------------------------------------------------

class TestBackupConfig:
    def test_encryption_enabled_when_key_set(self) -> None:
        cfg = BackupConfig(encryption_key="placeholder_will_be_replaced")
        assert cfg.is_encryption_enabled is True

    def test_encryption_not_enabled_without_key(self) -> None:
        cfg = BackupConfig()
        assert cfg.is_encryption_enabled is False

    def test_explicit_false_overrides_key(self) -> None:
        cfg = BackupConfig(encryption_key="placeholder_will_be_replaced", encryption_enabled=False)
        assert cfg.is_encryption_enabled is False

    def test_explicit_true_without_key_raises(self) -> None:
        with pytest.raises(ValidationError, match="BACKUP_ENCRYPTION_ENABLED"):
            BackupConfig(encryption_enabled=True)

    def test_default_safety_limits(self) -> None:
        cfg = BackupConfig()
        assert cfg.max_restore_bytes == 100 * 1024 * 1024
        assert cfg.max_zip_entries == 100
        assert cfg.max_compressed_bytes == 100 * 1024 * 1024
        assert cfg.max_decompressed_bytes == 500 * 1024 * 1024
        assert cfg.max_compression_ratio == 100.0


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
        import io
        import zipfile

        from app.infrastructure.persistence.backup_crypto import is_fernet_ciphertext

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        assert is_fernet_ciphertext(buf.getvalue()) is False


# ---------------------------------------------------------------------------
# ZIP safety
# ---------------------------------------------------------------------------

_LIMITS = {
    "max_entries": 10,
    "max_compressed_bytes": 10 * 1024 * 1024,
    "max_decompressed_bytes": 1000,
    "max_ratio": 50.0,
}


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

    def test_backslash_absolute_path_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        # Windows-style absolute path bypasses naive startswith("/") check
        with pytest.raises(ZipSafetyViolation, match="absolute"):
            validate_zip_safety(_one_entry_zip(filename="\\etc\\passwd"), **_LIMITS)

    def test_windows_drive_path_rejected(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        with pytest.raises(ZipSafetyViolation, match="absolute"):
            validate_zip_safety(_one_entry_zip(filename="C:/Windows/system32/evil.dll"), **_LIMITS)

    def test_corrupt_zip_raises_violation(self) -> None:
        from app.infrastructure.persistence.backup_safety import (
            ZipSafetyViolation,
            validate_zip_safety,
        )

        with pytest.raises(ZipSafetyViolation, match="corrupt"):
            validate_zip_safety(b"not a zip", **_LIMITS)


# ---------------------------------------------------------------------------
# Restore pipeline (decrypt + safety + import)
# ---------------------------------------------------------------------------

def _minimal_backup_zip() -> bytes:
    """Minimal valid backup ZIP with empty data arrays."""
    manifest = {
        "version": "1.0",
        "user_id": 1,
        "created_at": "2024-01-01T00:00:00+00:00",
        "counts": {
            "requests": 0, "summaries": 0, "tags": 0, "summary_tags": 0,
            "collections": 0, "collection_items": 0, "highlights": 0,
        },
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name in (
            "requests", "summaries", "tags", "summary_tags",
            "collections", "collection_items", "highlights",
        ):
            zf.writestr(f"{name}.json", "[]")
    return buf.getvalue()


def _make_mock_db() -> MagicMock:
    """Minimal DB mock that satisfies async_restore_from_archive."""
    @asynccontextmanager
    async def fake_transaction():
        session = MagicMock()
        session.scalar = AsyncMock(return_value=None)
        session.execute = AsyncMock(return_value=MagicMock())
        session.flush = AsyncMock()
        yield session

    db = MagicMock()
    db.transaction = fake_transaction
    return db


class TestRestoreHardening:
    async def test_restore_accepts_encrypted_archive(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_archive_service import (
            async_restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        encrypted = encrypt_backup(_minimal_backup_zip(), SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig(encryption_key=_TEST_KEY_STR)
        result = await async_restore_from_archive(1, encrypted, db=_make_mock_db(), cfg=cfg)
        assert result["errors"] == []
        assert result["restored"]["requests"] == 0

    async def test_restore_accepts_unencrypted_archive(self) -> None:
        from app.infrastructure.persistence.backup_archive_service import (
            async_restore_from_archive,
        )

        cfg = BackupConfig()
        result = await async_restore_from_archive(
            1, _minimal_backup_zip(), db=_make_mock_db(), cfg=cfg
        )
        assert result["errors"] == []

    async def test_restore_rejects_encrypted_without_key(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_archive_service import (
            async_restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        encrypted = encrypt_backup(_minimal_backup_zip(), SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig()  # no key
        result = await async_restore_from_archive(1, encrypted, cfg=cfg)
        assert any("BACKUP_ENCRYPTION_KEY" in e for e in result["errors"])

    async def test_restore_rejects_wrong_key(self) -> None:
        from pydantic import SecretStr

        from app.infrastructure.persistence.backup_archive_service import (
            async_restore_from_archive,
        )
        from app.infrastructure.persistence.backup_crypto import encrypt_backup

        encrypted = encrypt_backup(_minimal_backup_zip(), SecretStr(_TEST_KEY_STR))
        cfg = BackupConfig(encryption_key=_OTHER_KEY)
        result = await async_restore_from_archive(1, encrypted, cfg=cfg)
        assert any("decrypt" in e.lower() for e in result["errors"])

    async def test_restore_rejects_safety_violation(self) -> None:
        from app.infrastructure.persistence.backup_archive_service import (
            async_restore_from_archive,
        )

        # "a" * 5000 compresses to ~15 B → ratio ~333, exceeds default max_ratio=100
        bomb = _one_entry_zip(content=b"a" * 5000)
        cfg = BackupConfig()
        result = await async_restore_from_archive(1, bomb, cfg=cfg)
        assert len(result["errors"]) == 1
        assert "ratio" in result["errors"][0].lower()


# ---------------------------------------------------------------------------
# Upload cap (router helper)
# ---------------------------------------------------------------------------


class TestUploadCap:
    async def test_oversized_upload_rejected(self) -> None:
        from app.api.exceptions import APIException
        from app.api.routers.backups import _read_upload_capped

        mock_file = AsyncMock()
        # 50 + 60 = 110 bytes > limit of 100
        mock_file.read.side_effect = [b"a" * 50, b"b" * 60, b""]
        with pytest.raises(APIException) as exc_info:
            await _read_upload_capped(mock_file, limit=100)
        assert exc_info.value.status_code == 413

    async def test_within_limit_passes(self) -> None:
        from app.api.routers.backups import _read_upload_capped

        mock_file = AsyncMock()
        mock_file.read.side_effect = [b"hello world", b""]
        content = await _read_upload_capped(mock_file, limit=100)
        assert content == b"hello world"
