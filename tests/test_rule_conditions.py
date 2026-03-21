"""Tests for RuleConditionEvaluator from the rule engine domain service."""

from __future__ import annotations

import unittest

from app.domain.services.rule_engine import RuleConditionEvaluator


class TestDomainMatches(unittest.TestCase):
    def _eval(self, operator: str, value: str, url: str) -> bool:
        cond = {"type": "domain_matches", "operator": operator, "value": value}
        ctx = {"url": url}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_equals(self) -> None:
        assert self._eval("equals", "https://example.com", "https://example.com")
        assert not self._eval("equals", "https://example.com", "https://other.com")

    def test_contains(self) -> None:
        assert self._eval("contains", "example", "https://example.com/path")
        assert not self._eval("contains", "github", "https://example.com/path")

    def test_regex(self) -> None:
        assert self._eval("regex", r"example\.com", "https://example.com/page")
        assert not self._eval("regex", r"^github\.com$", "https://example.com")


class TestTitleContains(unittest.TestCase):
    def _eval(self, operator: str, value: str, title: str) -> bool:
        cond = {"type": "title_contains", "operator": operator, "value": value}
        ctx = {"title": title}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_contains_case_insensitive(self) -> None:
        assert self._eval("contains", "python", "Learn Python Today")
        assert not self._eval("contains", "rust", "Learn Python Today")

    def test_regex(self) -> None:
        assert self._eval("regex", r"Python\s+\d+", "Python 3 Tutorial")
        assert not self._eval("regex", r"^Rust", "Learn Python Today")


class TestHasTag(unittest.TestCase):
    def _eval(self, operator: str, value: list[str], tags: list[str]) -> bool:
        cond = {"type": "has_tag", "operator": operator, "value": value}
        ctx = {"tags": tags}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_any(self) -> None:
        assert self._eval("any", ["python", "rust"], ["python", "tutorial"])
        assert not self._eval("any", ["rust", "go"], ["python", "tutorial"])

    def test_all(self) -> None:
        assert self._eval("all", ["python", "tutorial"], ["python", "tutorial", "web"])
        assert not self._eval("all", ["python", "rust"], ["python", "tutorial"])

    def test_none(self) -> None:
        assert self._eval("none", ["rust", "go"], ["python", "tutorial"])
        assert not self._eval("none", ["python", "go"], ["python", "tutorial"])


class TestLanguageIs(unittest.TestCase):
    def _eval(self, operator: str, value: object, language: str) -> bool:
        cond = {"type": "language_is", "operator": operator, "value": value}
        ctx = {"language": language}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_equals(self) -> None:
        assert self._eval("equals", "en", "en")
        assert not self._eval("equals", "en", "ru")

    def test_in_list(self) -> None:
        assert self._eval("in", ["en", "ru"], "en")
        assert not self._eval("in", ["fr", "de"], "en")

    def test_in_comma_string(self) -> None:
        assert self._eval("in", "en,ru", "en")
        assert not self._eval("in", "fr,de", "en")


class TestReadingTime(unittest.TestCase):
    def _eval(self, operator: str, value: int, reading_time: int) -> bool:
        cond = {"type": "reading_time", "operator": operator, "value": value}
        ctx = {"reading_time": reading_time}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_gt(self) -> None:
        assert self._eval("gt", 5, 10)
        assert not self._eval("gt", 5, 3)

    def test_lt(self) -> None:
        assert self._eval("lt", 10, 5)
        assert not self._eval("lt", 5, 10)

    def test_eq(self) -> None:
        assert self._eval("eq", 5, 5)
        assert not self._eval("eq", 5, 10)


class TestSourceType(unittest.TestCase):
    def _eval(self, operator: str, value: object, source_type: str) -> bool:
        cond = {"type": "source_type", "operator": operator, "value": value}
        ctx = {"source_type": source_type}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_equals(self) -> None:
        assert self._eval("equals", "article", "article")
        assert not self._eval("equals", "article", "video")

    def test_in(self) -> None:
        assert self._eval("in", ["article", "video"], "article")
        assert not self._eval("in", ["video", "podcast"], "article")


class TestContentContains(unittest.TestCase):
    def _eval(self, operator: str, value: str, content: str) -> bool:
        cond = {"type": "content_contains", "operator": operator, "value": value}
        ctx = {"content": content}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        return matched

    def test_contains_case_insensitive(self) -> None:
        assert self._eval("contains", "machine learning", "An article about Machine Learning.")
        assert not self._eval("contains", "quantum", "An article about Machine Learning.")

    def test_regex(self) -> None:
        assert self._eval("regex", r"\d{4}-\d{2}-\d{2}", "Published on 2024-01-15")
        assert not self._eval("regex", r"^\d+$", "Not a number")


class TestEvaluateConditions(unittest.TestCase):
    def test_match_mode_all(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "example"},
            {"type": "title_contains", "operator": "contains", "value": "python"},
        ]
        ctx = {"url": "https://example.com", "title": "Learn Python"}
        matched, results = RuleConditionEvaluator.evaluate_conditions(
            conditions, ctx, match_mode="all"
        )
        assert matched
        assert all(r["matched"] for r in results)

    def test_match_mode_all_fails_when_one_false(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "example"},
            {"type": "title_contains", "operator": "contains", "value": "rust"},
        ]
        ctx = {"url": "https://example.com", "title": "Learn Python"}
        matched, _results = RuleConditionEvaluator.evaluate_conditions(
            conditions, ctx, match_mode="all"
        )
        assert not matched

    def test_match_mode_any(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "github"},
            {"type": "title_contains", "operator": "contains", "value": "python"},
        ]
        ctx = {"url": "https://example.com", "title": "Learn Python"}
        matched, _results = RuleConditionEvaluator.evaluate_conditions(
            conditions, ctx, match_mode="any"
        )
        assert matched

    def test_match_mode_any_all_false(self) -> None:
        conditions = [
            {"type": "domain_matches", "operator": "contains", "value": "github"},
            {"type": "title_contains", "operator": "contains", "value": "rust"},
        ]
        ctx = {"url": "https://example.com", "title": "Learn Python"}
        matched, _ = RuleConditionEvaluator.evaluate_conditions(conditions, ctx, match_mode="any")
        assert not matched


class TestEdgeCases(unittest.TestCase):
    def test_invalid_regex_does_not_crash(self) -> None:
        cond = {"type": "domain_matches", "operator": "regex", "value": "[invalid("}
        ctx = {"url": "https://example.com"}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        assert not matched

    def test_unknown_condition_type_returns_false(self) -> None:
        cond = {"type": "nonexistent_type", "operator": "equals", "value": "x"}
        ctx = {"url": "https://example.com"}
        matched, results = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        assert not matched
        assert results[0]["matched"] is False

    def test_empty_conditions_all_mode(self) -> None:
        matched, results = RuleConditionEvaluator.evaluate_conditions([], {}, match_mode="all")
        assert matched  # all() on empty is True
        assert results == []

    def test_empty_conditions_any_mode(self) -> None:
        matched, results = RuleConditionEvaluator.evaluate_conditions([], {}, match_mode="any")
        assert not matched  # any() on empty is False
        assert results == []

    def test_reading_time_invalid_value_does_not_crash(self) -> None:
        cond = {"type": "reading_time", "operator": "gt", "value": "not_a_number"}
        ctx = {"reading_time": 5}
        matched, _ = RuleConditionEvaluator.evaluate_conditions([cond], ctx)
        assert not matched


if __name__ == "__main__":
    unittest.main()
