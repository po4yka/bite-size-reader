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
    cfg = RuntimeConfig(migration_interface_backend="rust")
    assert cfg.migration_interface_backend == "rust"


def test_worker_backend_defaults_to_python() -> None:
    cfg = RuntimeConfig()
    assert cfg.migration_worker_backend == "python"


def test_worker_backend_accepts_rust() -> None:
    cfg = RuntimeConfig(migration_worker_backend="rust")
    assert cfg.migration_worker_backend == "rust"


def test_processing_orchestrator_timeout_defaults_to_five_minutes() -> None:
    cfg = RuntimeConfig()
    assert cfg.migration_processing_orchestrator_timeout_ms == 300000


def test_processing_orchestrator_timeout_accepts_long_running_execution_value() -> None:
    cfg = RuntimeConfig(migration_processing_orchestrator_timeout_ms=450000)
    assert cfg.migration_processing_orchestrator_timeout_ms == 450000


def test_worker_timeout_defaults_to_five_minutes() -> None:
    cfg = RuntimeConfig()
    assert cfg.migration_worker_timeout_ms == 300000
