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
