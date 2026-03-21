"""Tests for smart collection domain service."""

from __future__ import annotations

import unittest

from app.domain.services.smart_collection import (
    MAX_SMART_CONDITIONS,
    evaluate_summary,
    validate_smart_conditions,
)


class TestValidateSmartConditions(unittest.TestCase):
    def test_valid_single_condition(self) -> None:
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "arxiv.org"}]
        valid, err = validate_smart_conditions(conditions, "all")
        assert valid
        assert err is None

    def test_valid_multiple_conditions(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "arxiv.org"},
            {"type": "language_is", "operator": "equals", "value": "en"},
        ]
        valid, err = validate_smart_conditions(conditions, "any")
        assert valid
        assert err is None

    def test_empty_conditions_rejected(self) -> None:
        valid, err = validate_smart_conditions([], "all")
        assert not valid
        assert err is not None
        assert "at least one" in err.lower()

    def test_too_many_conditions(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": f"test{i}.com"}
            for i in range(MAX_SMART_CONDITIONS + 1)
        ]
        valid, err = validate_smart_conditions(conditions, "all")
        assert not valid
        assert err is not None
        assert "too many" in err.lower()

    def test_invalid_match_mode(self) -> None:
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "test.com"}]
        valid, err = validate_smart_conditions(conditions, "invalid")
        assert not valid
        assert err is not None
        assert "match_mode" in err.lower()

    def test_invalid_condition_type(self) -> None:
        conditions = [{"type": "nonexistent", "operator": "equals", "value": "test"}]
        valid, err = validate_smart_conditions(conditions, "all")
        assert not valid
        assert err is not None

    def test_missing_operator_field(self) -> None:
        conditions = [{"type": "domain_matches", "value": "test.com"}]
        valid, err = validate_smart_conditions(conditions, "all")
        assert not valid
        assert err is not None
        assert "operator" in err.lower()

    def test_missing_value_field(self) -> None:
        conditions = [{"type": "domain_matches", "operator": "contains"}]
        valid, err = validate_smart_conditions(conditions, "all")
        assert not valid
        assert err is not None
        assert "value" in err.lower()

    def test_missing_operator_and_value(self) -> None:
        conditions = [{"type": "domain_matches"}]
        valid, err = validate_smart_conditions(conditions, "all")
        assert not valid
        assert err is not None

    def test_max_conditions_exactly_at_limit(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": f"test{i}.com"}
            for i in range(MAX_SMART_CONDITIONS)
        ]
        valid, err = validate_smart_conditions(conditions, "all")
        assert valid
        assert err is None


class TestEvaluateSummary(unittest.TestCase):
    _full_ctx: dict = {
        "url": "",
        "title": "",
        "tags": [],
        "language": "",
        "reading_time": 0,
        "source_type": "",
        "content": "",
    }

    def _ctx(self, **overrides: object) -> dict:
        ctx = dict(self._full_ctx)
        ctx.update(overrides)
        return ctx

    def test_matches_domain(self) -> None:
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "arxiv"}]
        assert evaluate_summary(conditions, self._ctx(url="https://arxiv.org/abs/1234"), "all")

    def test_no_match(self) -> None:
        conditions = [{"type": "domain_matches", "operator": "contains", "value": "github"}]
        assert not evaluate_summary(conditions, self._ctx(url="https://arxiv.org/abs/1234"), "all")

    def test_match_mode_all_requires_all(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "arxiv"},
            {"type": "language_is", "operator": "equals", "value": "en"},
        ]
        ctx = self._ctx(url="https://arxiv.org", language="ru")
        assert not evaluate_summary(conditions, ctx, "all")

    def test_match_mode_any_needs_one(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "arxiv"},
            {"type": "language_is", "operator": "equals", "value": "en"},
        ]
        ctx = self._ctx(url="https://arxiv.org", language="ru")
        assert evaluate_summary(conditions, ctx, "any")

    def test_tag_condition(self) -> None:
        conditions = [{"type": "has_tag", "operator": "any", "value": ["ml", "ai"]}]
        ctx = self._ctx(tags=["ml", "python"])
        assert evaluate_summary(conditions, ctx, "all")

    def test_reading_time_gt(self) -> None:
        conditions = [{"type": "reading_time", "operator": "gt", "value": 10}]
        ctx = self._ctx(reading_time=15)
        assert evaluate_summary(conditions, ctx, "all")

    def test_reading_time_lt_no_match(self) -> None:
        conditions = [{"type": "reading_time", "operator": "lt", "value": 5}]
        ctx = self._ctx(reading_time=15)
        assert not evaluate_summary(conditions, ctx, "all")

    def test_empty_conditions_all_mode(self) -> None:
        # all() on empty iterable is True (vacuous truth)
        assert evaluate_summary([], self._ctx(), "all") is True

    def test_empty_conditions_any_mode(self) -> None:
        # any() on empty iterable is False
        assert evaluate_summary([], self._ctx(), "any") is False


if __name__ == "__main__":
    unittest.main()
