"""Unit tests for backup hardening: config, crypto, safety, restore pipeline."""

from __future__ import annotations

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
