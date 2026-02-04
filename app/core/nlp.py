"""NLP utilities: readability scoring and keyword extraction.

Extracted from summary_contract.py. The TF-IDF extraction has a soft
dependency on scikit-learn with a stdlib fallback.
"""

from __future__ import annotations

import re


def compute_flesch_reading_ease(text: str) -> float:
    """Compute Flesch Reading Ease score directly.

    Formula: 206.835 - 1.015 * (total words / total sentences) - 84.6 * (total syllables / total words)

    Returns a score from 0-100 (higher = easier to read).
    """
    if not isinstance(text, str) or not text.strip():
        return 0.0

    # Count sentences (split on .!?)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    num_sentences = len(sentences) if sentences else 1

    # Count words
    words = re.findall(r"\b\w+\b", text.lower())
    num_words = len(words) if words else 1

    # Estimate syllables (simple heuristic: count vowel groups)
    def count_syllables(word: str) -> int:
        word = word.lower()
        vowels = "aeiouy"
        syllable_count = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel

        # Adjust for silent 'e' at end
        if word.endswith("e") and syllable_count > 1:
            syllable_count -= 1

        # Every word has at least 1 syllable
        return max(1, syllable_count)

    total_syllables = sum(count_syllables(word) for word in words)

    # Compute Flesch Reading Ease
    try:
        score = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (total_syllables / num_words)
        # Clamp to 0-100 range
        return max(0.0, min(100.0, score))
    except (ZeroDivisionError, ValueError):
        return 0.0


def extract_keywords_tfidf(text: str, topn: int = 10) -> list[str]:
    """Extract keywords using TF-IDF from scikit-learn.

    Args:
        text: Input text to extract keywords from
        topn: Number of top keywords to return

    Returns:
        List of keyword strings
    """
    if not isinstance(text, str) or not text.strip():
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        # Use TF-IDF with n-grams (1-3 words)
        vectorizer = TfidfVectorizer(
            max_features=topn * 3,  # Extract more candidates
            ngram_range=(1, 3),  # 1-3 word phrases
            stop_words="english",
            lowercase=True,
            min_df=1,
            max_df=1.0,
        )

        # Fit and transform (needs at least 1 document)
        tfidf_matrix = vectorizer.fit_transform([text])
        feature_names = vectorizer.get_feature_names_out()

        # Get scores for the single document
        scores = tfidf_matrix.toarray()[0]

        # Sort by score and get top keywords
        scored_terms = [(feature_names[i], scores[i]) for i in range(len(scores))]
        scored_terms.sort(key=lambda x: x[1], reverse=True)

        # Return top n terms
        return [term for term, score in scored_terms[:topn] if term.strip()]

    except Exception:
        # Fallback: extract most common words (simple frequency)
        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
        # Remove common stop words
        stop_words = {
            "this",
            "that",
            "with",
            "from",
            "have",
            "they",
            "what",
            "been",
            "will",
            "would",
            "there",
            "their",
            "about",
            "which",
            "when",
            "make",
            "like",
            "time",
            "just",
            "know",
            "take",
            "into",
            "year",
            "some",
            "could",
            "them",
            "other",
            "than",
            "then",
            "look",
            "only",
            "come",
            "over",
            "also",
            "back",
            "after",
            "work",
            "first",
            "well",
            "even",
            "want",
            "because",
            "these",
            "give",
            "most",
            "very",
        }
        words = [w for w in words if w not in stop_words]

        # Count frequency
        from collections import Counter

        word_counts = Counter(words)
        return [word for word, count in word_counts.most_common(topn)]
