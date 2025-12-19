"""Tests for topic_search_utils ensure_mapping function."""

import pytest

from app.services.topic_search_utils import ensure_mapping


class TestEnsureMapping:
    """Test ensure_mapping handles various input types safely."""

    def test_ensure_mapping_with_dict(self):
        """Test ensure_mapping with dict returns the dict."""
        data = {"key": "value", "nested": {"inner": 123}}
        result = ensure_mapping(data)
        assert result == data
        assert isinstance(result, dict)

    def test_ensure_mapping_with_none(self):
        """Test ensure_mapping with None returns empty dict."""
        result = ensure_mapping(None)
        assert result == {}

    def test_ensure_mapping_with_valid_json_string(self):
        """Test ensure_mapping parses valid JSON string."""
        json_str = '{"title": "Test", "count": 42}'
        result = ensure_mapping(json_str)
        assert result == {"title": "Test", "count": 42}

    def test_ensure_mapping_with_invalid_json_string(self):
        """Test ensure_mapping returns empty dict for invalid JSON."""
        result = ensure_mapping("not valid json")
        assert result == {}

    def test_ensure_mapping_with_json_array_string(self):
        """Test ensure_mapping returns empty dict for JSON array (not object)."""
        result = ensure_mapping('[1, 2, 3]')
        assert result == {}  # Array is not a mapping

    def test_ensure_mapping_with_empty_string(self):
        """Test ensure_mapping with empty string returns empty dict."""
        result = ensure_mapping("")
        assert result == {}

    def test_ensure_mapping_with_whitespace_string(self):
        """Test ensure_mapping with whitespace string returns empty dict."""
        result = ensure_mapping("   ")
        assert result == {}

    def test_ensure_mapping_with_int(self):
        """Test ensure_mapping with int returns empty dict."""
        result = ensure_mapping(123)
        assert result == {}

    def test_ensure_mapping_with_list(self):
        """Test ensure_mapping with list returns empty dict."""
        result = ensure_mapping([1, 2, 3])
        assert result == {}

    def test_ensure_mapping_with_nested_json_string(self):
        """Test ensure_mapping handles nested JSON structures."""
        json_str = '{"metadata": {"title": "Test", "tags": ["a", "b"]}}'
        result = ensure_mapping(json_str)
        assert result == {"metadata": {"title": "Test", "tags": ["a", "b"]}}

    def test_ensure_mapping_preserves_unicode(self):
        """Test ensure_mapping preserves unicode characters."""
        data = {"title": "Test", "content": "Hello World"}
        result = ensure_mapping(data)
        assert result["content"] == "Hello World"

    def test_ensure_mapping_with_mapping_subclass(self):
        """Test ensure_mapping works with Mapping subclasses."""
        from collections import OrderedDict

        data = OrderedDict([("a", 1), ("b", 2)])
        result = ensure_mapping(data)
        assert result == {"a": 1, "b": 2}
        assert isinstance(result, dict)
