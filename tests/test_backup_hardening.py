"""Unit tests for backup hardening: config, crypto, safety, restore pipeline."""

from __future__ import annotations

import io
import zipfile

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
