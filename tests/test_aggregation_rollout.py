from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

import pytest

from app.application.services.aggregation_rollout import (
    AggregationRolloutGate,
    AggregationRolloutStage,
)
from app.config.runtime import RuntimeConfig

if TYPE_CHECKING:
    from app.config import AppConfig


def _cfg(
    *,
    enabled: bool = True,
    stage: str = "enabled",
    allowed_user_ids: tuple[int, ...] = (),
) -> AppConfig:
    return cast(
        "AppConfig",
        SimpleNamespace(
            runtime=SimpleNamespace(
                aggregation_bundle_enabled=enabled,
                aggregation_rollout_stage=stage,
                aggregation_meta_extractors_enabled=True,
            ),
            telegram=SimpleNamespace(allowed_user_ids=allowed_user_ids),
        ),
    )


def test_runtime_config_validates_aggregation_rollout_stage() -> None:
    cfg = RuntimeConfig(aggregation_rollout_stage="owner_beta")
    assert cfg.aggregation_rollout_stage == "owner_beta"

    with pytest.raises(ValueError, match="Aggregation rollout stage must be one of"):
        RuntimeConfig(aggregation_rollout_stage="invalid-stage")


@pytest.mark.asyncio
async def test_rollout_gate_respects_disabled_and_internal_modes() -> None:
    disabled_gate = AggregationRolloutGate(cfg=_cfg(enabled=False))
    disabled = await disabled_gate.evaluate(1)
    assert disabled.enabled is False
    assert disabled.stage == AggregationRolloutStage.DISABLED

    internal_gate = AggregationRolloutGate(cfg=_cfg(stage="internal", allowed_user_ids=(7, 8)))
    assert (await internal_gate.evaluate(7)).enabled is True
    internal_denied = await internal_gate.evaluate(99)
    assert internal_denied.enabled is False
    assert "internal allowlisted accounts" in internal_denied.reason


@pytest.mark.asyncio
async def test_rollout_gate_requires_owner_for_owner_beta() -> None:
    user_repo = SimpleNamespace(
        async_get_user_by_telegram_id=AsyncMock(
            side_effect=[
                {"telegram_user_id": 1, "is_owner": True},
                {"telegram_user_id": 2, "is_owner": False},
            ]
        )
    )
    gate = AggregationRolloutGate(
        cfg=_cfg(stage="owner_beta"),
        user_repo=cast("Any", user_repo),
    )

    assert (await gate.evaluate(1)).enabled is True
    denied = await gate.evaluate(2)
    assert denied.enabled is False
    assert denied.stage == AggregationRolloutStage.OWNER_BETA
    assert "owner-only beta" in denied.reason
