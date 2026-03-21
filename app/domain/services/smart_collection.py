"""Smart collection domain service.

Validates and evaluates conditions for query-based auto-collections.
Reuses RuleConditionEvaluator from the rule engine.
"""

from __future__ import annotations

from app.domain.services.rule_engine import (
    RuleConditionEvaluator,
    validate_condition,
)

MAX_SMART_COLLECTIONS_PER_USER = 20
MAX_SMART_CONDITIONS = 5
MAX_EVALUATION_BATCH = 10000

VALID_MATCH_MODES = frozenset({"all", "any"})


def validate_smart_conditions(
    conditions: list[dict], match_mode: str = "all"
) -> tuple[bool, str | None]:
    """Validate conditions for a smart collection.

    Returns (is_valid, error_message).
    """
    if match_mode not in VALID_MATCH_MODES:
        return False, f"Invalid match_mode: {match_mode}. Must be 'all' or 'any'."

    if not conditions:
        return False, "Smart collections must have at least one condition."

    if len(conditions) > MAX_SMART_CONDITIONS:
        return False, f"Too many conditions ({len(conditions)}). Maximum is {MAX_SMART_CONDITIONS}."

    for i, cond in enumerate(conditions):
        valid, err = validate_condition(cond)
        if not valid:
            return False, f"Condition {i + 1}: {err}"

    return True, None


def evaluate_summary(conditions: list[dict], context: dict, match_mode: str = "all") -> bool:
    """Evaluate a summary context against smart collection conditions.

    Returns True if the summary matches.
    """
    matched, _ = RuleConditionEvaluator.evaluate_conditions(conditions, context, match_mode)
    return matched
