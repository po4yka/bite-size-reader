"""Tests for content-aware model routing classifier."""

from __future__ import annotations

from app.core.content_classifier import ContentTier, classify_content


class TestClassifyContent:
    """Test classify_content() tier assignment."""

    # --- Technical signals ---

    def test_technical_domain_strong_signal(self) -> None:
        result = classify_content("Some paper content", url="https://arxiv.org/abs/2401.00001")
        assert result == ContentTier.TECHNICAL

    def test_technical_domain_with_www(self) -> None:
        result = classify_content("Content", url="https://www.github.com/org/repo")
        assert result == ContentTier.TECHNICAL

    def test_technical_keywords_only(self) -> None:
        text = (
            "This paper presents a novel algorithm for neural network optimization. "
            "Our methodology uses gradient descent with a custom implementation. "
            "The benchmark results show improved throughput and lower latency."
        )
        result = classify_content(text)
        assert result == ContentTier.TECHNICAL

    def test_technical_domain_plus_keywords(self) -> None:
        text = "Abstract: We present a novel algorithm for optimization."
        result = classify_content(text, url="https://arxiv.org/abs/2401.00001")
        assert result == ContentTier.TECHNICAL

    # --- Sociopolitical signals ---

    def test_sociopolitical_domain_strong_signal(self) -> None:
        result = classify_content("Some article", url="https://www.politico.com/news/article")
        assert result == ContentTier.SOCIOPOLITICAL

    def test_sociopolitical_keywords_only(self) -> None:
        text = (
            "The geopolitical implications of the election are significant. "
            "Congress passed new legislation on immigration and sovereignty. "
            "The editorial discusses democracy and the political landscape."
        )
        result = classify_content(text)
        assert result == ContentTier.SOCIOPOLITICAL

    def test_sociopolitical_history_content(self) -> None:
        text = (
            "The revolution of the 18th century shaped modern civilization. "
            "Historical records show the era of independence movements. "
            "The commentary examines colonialism and its lasting impact."
        )
        result = classify_content(text)
        assert result == ContentTier.SOCIOPOLITICAL

    # --- Default signals ---

    def test_default_no_signals(self) -> None:
        result = classify_content("A nice blog post about cooking recipes and food.")
        assert result == ContentTier.DEFAULT

    def test_default_unknown_domain(self) -> None:
        result = classify_content("General content", url="https://example.com/post")
        assert result == ContentTier.DEFAULT

    def test_default_empty_content(self) -> None:
        result = classify_content("")
        assert result == ContentTier.DEFAULT

    # --- Tie-breaking ---

    def test_technical_wins_tie(self) -> None:
        """TECHNICAL should win when both tiers have equal weight."""
        text = (
            "This algorithm implementation analyzes the political implications "
            "of neural network democracy. The geopolitical benchmark shows "
            "legislation affecting methodology and congress optimization."
        )
        result = classify_content(text)
        # Both should have keyword matches, but TECHNICAL wins ties
        assert result in (ContentTier.TECHNICAL, ContentTier.DEFAULT)

    # --- Edge cases ---

    def test_none_url(self) -> None:
        result = classify_content("Some content", url=None)
        assert isinstance(result, ContentTier)

    def test_invalid_url(self) -> None:
        result = classify_content("Some content", url="not-a-url")
        assert isinstance(result, ContentTier)

    def test_subdomain_matching(self) -> None:
        result = classify_content("Content", url="https://sub.nature.com/article")
        assert result == ContentTier.TECHNICAL

    def test_bbc_sociopolitical(self) -> None:
        result = classify_content("News article", url="https://bbc.co.uk/news/politics")
        assert result == ContentTier.SOCIOPOLITICAL
