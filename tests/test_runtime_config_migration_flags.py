from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.runtime import RuntimeConfig


def test_m3_shadow_mode_defaults_to_enabled() -> None:
    cfg = RuntimeConfig()
    assert cfg.migration_shadow_mode_enabled is True


def test_m3_shadow_mode_disallows_disabled_value() -> None:
    with pytest.raises(ValidationError, match="MIGRATION_SHADOW_MODE_ENABLED must be true"):
        RuntimeConfig(migration_shadow_mode_enabled=False)


def test_m6_telegram_runtime_timeout_defaults_to_expected_value() -> None:
    cfg = RuntimeConfig()
    assert cfg.migration_telegram_runtime_timeout_ms == 150


def test_m6_telegram_runtime_timeout_accepts_valid_value() -> None:
    cfg = RuntimeConfig(migration_telegram_runtime_timeout_ms=200)
    assert cfg.migration_telegram_runtime_timeout_ms == 200


def test_m6_telegram_runtime_legacy_backend_toggle_is_ignored() -> None:
    cfg = RuntimeConfig(migration_telegram_runtime_backend="python")
    assert "migration_telegram_runtime_backend" not in cfg.model_dump()
