"""Tests for the soft-failure escalation policy.

Distinguishes "soft" failures (well-formed HTTP 200 but JSON parse
error, schema validation failure, or low-confidence) from "hard"
failures (4xx/5xx, network errors). On a soft failure the retry loop
should advance to the next model in the tier-specific fallback chain
rather than burn the retry budget on the same model that just produced
malformed output. A budget cap prevents runaway escalation cost.
"""

from __future__ import annotations

import pytest

from app.core.escalation_policy import (
    EscalationBudgetExceeded,
    EscalationDecision,
    EscalationPolicy,
    SoftFailureReason,
)


class TestSoftFailureDetection:
    def test_json_parse_failure_is_soft(self) -> None:
        assert (
            EscalationPolicy.classify_failure(
                http_status=200,
                json_parse_error=True,
                schema_validation_error=False,
            )
            is SoftFailureReason.JSON_PARSE_ERROR
        )

    def test_schema_validation_failure_is_soft(self) -> None:
        assert (
            EscalationPolicy.classify_failure(
                http_status=200,
                json_parse_error=False,
                schema_validation_error=True,
            )
            is SoftFailureReason.SCHEMA_VALIDATION_ERROR
        )

    def test_http_4xx_is_not_soft(self) -> None:
        assert (
            EscalationPolicy.classify_failure(
                http_status=429,
                json_parse_error=False,
                schema_validation_error=False,
            )
            is None
        )

    def test_http_5xx_is_not_soft(self) -> None:
        assert (
            EscalationPolicy.classify_failure(
                http_status=502,
                json_parse_error=False,
                schema_validation_error=False,
            )
            is None
        )

    def test_clean_response_is_not_soft(self) -> None:
        assert (
            EscalationPolicy.classify_failure(
                http_status=200,
                json_parse_error=False,
                schema_validation_error=False,
            )
            is None
        )


class TestDecision:
    def test_first_soft_failure_escalates(self) -> None:
        policy = EscalationPolicy(max_escalations=2)
        decision = policy.on_soft_failure(
            model="cheap-flash",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=("strong-pro",),
        )
        assert decision == EscalationDecision(advance_model=True, next_model="strong-pro")

    def test_no_remaining_fallback_does_not_escalate(self) -> None:
        policy = EscalationPolicy(max_escalations=2)
        decision = policy.on_soft_failure(
            model="cheap-flash",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=(),
        )
        # No model to advance to → caller should fall back to same-model retry.
        assert decision == EscalationDecision(advance_model=False, next_model=None)

    def test_budget_cap_blocks_further_escalation(self) -> None:
        policy = EscalationPolicy(max_escalations=2)
        # Burn the budget.
        policy.on_soft_failure(
            model="m1",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=("m2",),
        )
        policy.on_soft_failure(
            model="m2",
            reason=SoftFailureReason.SCHEMA_VALIDATION_ERROR,
            remaining_fallbacks=("m3",),
        )
        with pytest.raises(EscalationBudgetExceeded):
            policy.on_soft_failure(
                model="m3",
                reason=SoftFailureReason.JSON_PARSE_ERROR,
                remaining_fallbacks=("m4",),
            )

    def test_used_escalations_starts_at_zero(self) -> None:
        policy = EscalationPolicy(max_escalations=2)
        assert policy.used_escalations == 0

    def test_used_escalations_increments(self) -> None:
        policy = EscalationPolicy(max_escalations=3)
        policy.on_soft_failure(
            model="m1",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=("m2",),
        )
        assert policy.used_escalations == 1
        policy.on_soft_failure(
            model="m2",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=("m3",),
        )
        assert policy.used_escalations == 2

    def test_no_remaining_fallback_does_not_burn_budget(self) -> None:
        policy = EscalationPolicy(max_escalations=2)
        policy.on_soft_failure(
            model="m1",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=(),
        )
        assert policy.used_escalations == 0


class TestBudgetValidation:
    def test_zero_budget_disables_escalation(self) -> None:
        policy = EscalationPolicy(max_escalations=0)
        with pytest.raises(EscalationBudgetExceeded):
            policy.on_soft_failure(
                model="m1",
                reason=SoftFailureReason.JSON_PARSE_ERROR,
                remaining_fallbacks=("m2",),
            )

    def test_negative_budget_rejected(self) -> None:
        with pytest.raises(ValueError):
            EscalationPolicy(max_escalations=-1)


class TestConfigDefault:
    def test_config_exposes_max_escalations(self) -> None:
        from app.config.llm import ModelRoutingConfig

        cfg = ModelRoutingConfig()
        assert cfg.max_escalations == 2


class TestObservability:
    def test_each_escalation_emits_audit_event(self) -> None:
        events: list[dict] = []
        policy = EscalationPolicy(
            max_escalations=2,
            audit=lambda payload: events.append(payload),
            correlation_id="abc-123",
        )
        policy.on_soft_failure(
            model="cheap-flash",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=("strong-pro",),
        )
        assert len(events) == 1
        evt = events[0]
        assert evt["from_model"] == "cheap-flash"
        assert evt["to_model"] == "strong-pro"
        assert evt["reason"] == "json_parse_error"
        assert evt["correlation_id"] == "abc-123"

    def test_no_event_when_no_fallback_remaining(self) -> None:
        events: list[dict] = []
        policy = EscalationPolicy(
            max_escalations=2,
            audit=lambda payload: events.append(payload),
        )
        policy.on_soft_failure(
            model="m1",
            reason=SoftFailureReason.JSON_PARSE_ERROR,
            remaining_fallbacks=(),
        )
        assert events == []
