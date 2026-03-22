# ruff: noqa: RUF059
import pytest

from app.domain.services.tag_service import (
    normalize_tag_name,
    validate_tag_color,
    validate_tag_name,
)


class TestNormalizeTagName:
    def test_lowercase_and_preserve_spaces(self):
        assert normalize_tag_name("Machine Learning") == "machine learning"

    def test_strip_and_collapse_spaces(self):
        assert normalize_tag_name("  extra  spaces  ") == "extra spaces"

    def test_uppercase(self):
        assert normalize_tag_name("UPPERCASE") == "uppercase"

    def test_empty_string(self):
        assert normalize_tag_name("") == ""

    def test_whitespace_only(self):
        assert normalize_tag_name("  ") == ""


class TestValidateTagName:
    @pytest.mark.parametrize(
        "name",
        [
            "python",
            "machine-learning",
            "a",
            "x" * 100,
        ],
    )
    def test_valid_names(self, name):
        valid, error = validate_tag_name(name)
        assert valid is True
        assert error is None

    def test_empty_name(self):
        valid, error = validate_tag_name("")
        assert valid is False
        assert "empty" in error

    def test_too_long(self):
        valid, error = validate_tag_name("x" * 101)
        assert valid is False
        assert "100" in error

    def test_forbidden_hash(self):
        valid, error = validate_tag_name("#hashtag")
        assert valid is False
        assert "#" in error or "cannot contain" in error

    def test_forbidden_at(self):
        valid, error = validate_tag_name("@mention")
        assert valid is False
        assert "@" in error or "cannot contain" in error


class TestValidateTagColor:
    @pytest.mark.parametrize(
        "color",
        [
            None,
            "#3B82F6",
            "#000000",
            "#ffffff",
        ],
    )
    def test_valid_colors(self, color):
        valid, error = validate_tag_color(color)
        assert valid is True
        assert error is None

    def test_rejects_named_color(self):
        valid, error = validate_tag_color("red")
        assert valid is False

    def test_rejects_bad_hex_chars(self):
        valid, error = validate_tag_color("#GGG")
        assert valid is False

    def test_rejects_missing_hash(self):
        valid, error = validate_tag_color("3B82F6")
        assert valid is False

    def test_rejects_wrong_length(self):
        valid, error = validate_tag_color("#12345")
        assert valid is False
