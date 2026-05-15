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
