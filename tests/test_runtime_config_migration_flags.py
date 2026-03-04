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
