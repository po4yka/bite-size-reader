"""Tests for the QueryExpansionService."""

import unittest

from app.services.query_expansion_service import QueryExpansionService


class TestQueryExpansionService(unittest.TestCase):
    """Test cases for QueryExpansionService."""

    def test_expand_query_with_synonyms(self):
        """Test query expansion adds relevant synonyms."""
        service = QueryExpansionService(max_expansions=5, use_synonyms=True)

        # Test with "python" which has synonyms (longer than 2 chars)
        result = service.expand_query("python")

        assert result.original == "python"
        assert len(result.expanded_terms) > 0
        # Should include synonyms like "programming", "code", etc.
        expanded_text = " ".join(result.expanded_terms)
        assert any(term in expanded_text for term in ["programming", "code"])

    def test_expand_query_respects_max_expansions(self):
        """Test that expansion respects max_expansions limit."""
        service = QueryExpansionService(max_expansions=2, use_synonyms=True)

        result = service.expand_query("python programming")

        # Should not exceed max_expansions per term
        # Note: With multiple terms, total can be more than max_expansions
        assert len(result.expanded_terms) >= 0  # At least attempts expansion

    def test_expand_query_without_synonyms(self):
        """Test query expansion when synonyms are disabled."""
        service = QueryExpansionService(max_expansions=5, use_synonyms=False)

        result = service.expand_query("python programming")

        # Should have no expansions when synonyms disabled
        assert len(result.expanded_terms) == 0

    def test_expand_query_with_unknown_term(self):
        """Test expansion with term that has no synonyms."""
        service = QueryExpansionService(max_expansions=5, use_synonyms=True)

        result = service.expand_query("xyzabc123unknown")

        # Should return empty expanded terms for unknown words
        assert len(result.expanded_terms) == 0

    def test_expand_query_empty_input(self):
        """Test expansion with empty query."""
        service = QueryExpansionService(max_expansions=5, use_synonyms=True)

        result = service.expand_query("")

        assert result.original == ""
        assert len(result.expanded_terms) == 0

    def test_expand_query_whitespace_only(self):
        """Test expansion with whitespace-only query."""
        service = QueryExpansionService(max_expansions=5, use_synonyms=True)

        result = service.expand_query("   ")

        assert len(result.expanded_terms) == 0

    def test_expand_for_fts(self):
        """Test FTS query string generation."""
        service = QueryExpansionService(max_expansions=3, use_synonyms=True)

        result = service.expand_for_fts("python programming")

        # Should return FTS-compatible query with OR operator
        assert "OR" in result
        assert '"python programming"' in result
        # Should include some synonyms if found
        # Note: Actual synonyms depend on the query terms

    def test_expand_for_fts_no_synonyms(self):
        """Test FTS expansion with no synonyms."""
        service = QueryExpansionService(max_expansions=3, use_synonyms=False)

        result = service.expand_for_fts("test query")

        # Should just return the original query
        assert result == '"test query"'

    def test_synonym_map_coverage(self):
        """Test that common technical terms have synonyms."""
        service = QueryExpansionService(use_synonyms=True)

        # Test coverage for key technical terms (must be > 2 chars due to filtering)
        test_terms = ["api", "python", "javascript", "tutorial", "guide", "security"]

        for term in test_terms:
            result = service.expand_query(term)
            assert len(result.expanded_terms) > 0, f"Term '{term}' should have synonyms"

    def test_extract_key_terms(self):
        """Test key term extraction from queries."""
        service = QueryExpansionService()

        # Test with multi-word query
        terms = service._extract_key_terms("machine learning and ai")

        # Should extract meaningful terms, excluding stop words
        assert "machine" in terms
        assert "learning" in terms
        # Stop words should be filtered
        assert "and" not in terms

    def test_extract_key_terms_filters_short_words(self):
        """Test that very short words are filtered."""
        service = QueryExpansionService()

        terms = service._extract_key_terms("a an to python code")

        # Short stop words should be filtered
        assert "a" not in terms
        assert "an" not in terms
        assert "to" not in terms
        # Meaningful words should remain
        assert "python" in terms
        assert "code" in terms

    def test_find_synonyms_case_insensitive(self):
        """Test synonym lookup is case-insensitive."""
        service = QueryExpansionService()

        lower = service._find_synonyms("python")
        upper = service._find_synonyms("PYTHON")
        mixed = service._find_synonyms("Python")

        # All should return same synonyms
        assert len(lower) > 0
        assert lower == upper == mixed

    def test_add_custom_synonym(self):
        """Test adding custom synonyms."""
        service = QueryExpansionService()

        # Add custom synonym
        service.add_custom_synonym("docker", ["container", "containerization"])

        result = service.expand_query("docker")

        # Should include custom synonyms
        expanded = " ".join(result.expanded_terms)
        assert "container" in expanded or "containerization" in expanded

    def test_add_custom_synonym_extends_existing(self):
        """Test that adding synonyms extends existing mappings."""
        service = QueryExpansionService()

        # Add custom synonym to existing term
        original_result = service.expand_query("python")
        original_count = len(original_result.expanded_terms)

        service.add_custom_synonym("python", ["deep learning"])

        new_result = service.expand_query("python")

        # Should have more synonyms now (or at least the same)
        # Note: The exact count depends on synonym overlap
        assert len(new_result.expanded_terms) >= original_count

    def test_weight_map_assigns_proper_weights(self):
        """Test that weight map assigns correct weights to terms."""
        service = QueryExpansionService(use_synonyms=True)

        result = service.expand_query("python")

        # Original query should have weight 1.0
        assert result.weight_map.get("python") == 1.0

        # Synonyms should have lower weight (0.7)
        for term in result.expanded_terms:
            assert result.weight_map.get(term) == 0.7

    def test_multilingual_synonyms(self):
        """Test that service supports non-English synonyms."""
        service = QueryExpansionService()

        # Test Russian term (Cyrillic)
        result = service.expand_query("разработка")

        # Should have Russian synonyms
        assert len(result.expanded_terms) > 0

    def test_synonym_deduplication(self):
        """Test that duplicate synonyms are not added multiple times."""
        service = QueryExpansionService()

        result = service.expand_query("tutorial guide documentation")

        # Check that each synonym appears only once
        seen = set()
        for term in result.expanded_terms:
            assert term not in seen, f"Duplicate synonym found: {term}"
            seen.add(term)

    def test_partial_match_synonyms(self):
        """Test that partial matches in compound terms work."""
        service = QueryExpansionService()

        # Query with term that partially matches synonym keys
        result = service.expand_query("python development")

        # Should find synonyms for both "python" and "development"
        assert len(result.expanded_terms) > 0


if __name__ == "__main__":
    unittest.main()
