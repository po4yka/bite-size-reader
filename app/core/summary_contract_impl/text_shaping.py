from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from typing import Any

from app.core.summary_contract_impl.common import SummaryJSON, clean_string_list, is_numeric
from app.core.summary_text_utils import (
    cap_text as _cap_text,
    dedupe_case_insensitive as _dedupe_case_insensitive,
)


def normalize_readability_score(score: Any) -> float:
    """Normalize readability score precision for deterministic repeated shaping."""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):
        return 0.0
    return round(numeric, 6)


def compute_flesch_reading_ease(text: str) -> float:
    """Compute Flesch Reading Ease score directly."""
    if not isinstance(text, str) or not text.strip():
        return 0.0

    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    num_sentences = len(sentences) if sentences else 1

    words = re.findall(r"\b\w+\b", text.lower())
    num_words = len(words) if words else 1

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

        if word.endswith("e") and syllable_count > 1:
            syllable_count -= 1

        return max(1, syllable_count)

    total_syllables = sum(count_syllables(word) for word in words)

    try:
        score = 206.835 - 1.015 * (num_words / num_sentences) - 84.6 * (total_syllables / num_words)
        return max(0.0, min(100.0, score))
    except (ZeroDivisionError, ValueError):
        return 0.0


def extract_keywords_tfidf(text: str, topn: int = 10) -> list[str]:
    """Extract keywords using TF-IDF from scikit-learn."""
    if not isinstance(text, str) or not text.strip():
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            max_features=topn * 3,
            ngram_range=(1, 3),
            stop_words="english",
            lowercase=True,
            min_df=1,
            max_df=1.0,
        )
        tfidf_matrix = vectorizer.fit_transform([text])
        feature_names = vectorizer.get_feature_names_out()
        scores = tfidf_matrix.toarray()[0]
        scored_terms = [(feature_names[i], scores[i]) for i in range(len(scores))]
        scored_terms.sort(key=lambda x: x[1], reverse=True)
        return [term for term, score in scored_terms[:topn] if term.strip()]
    except Exception:
        words = re.findall(r"\b[a-z]{4,}\b", text.lower())
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
        words = [word for word in words if word not in stop_words]
        word_counts = Counter(words)
        return [word for word, count in word_counts.most_common(topn)]


def normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip()


def similarity_ratio(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


def tldr_needs_enrichment(tldr: str, summary_1000: str) -> bool:
    tldr_norm = normalize_whitespace(tldr)
    summary_norm = normalize_whitespace(summary_1000)

    if not tldr_norm or not summary_norm:
        return False

    if tldr_norm == summary_norm:
        return True

    similarity = similarity_ratio(tldr_norm, summary_norm)
    if similarity >= 0.92:
        return True

    if summary_norm.startswith(tldr_norm) or tldr_norm.startswith(summary_norm):
        if abs(len(tldr_norm) - len(summary_norm)) <= 120:
            return True

    return len(tldr_norm) <= len(summary_norm) + 40


def summary_fallback_from_supporting_fields(payload: SummaryJSON) -> str | None:
    """Compose a fallback summary using secondary textual fields."""

    def add_snippet(snippet: Any) -> None:
        if len(snippets) >= 8:
            return
        text = str(snippet).strip() if snippet is not None else ""
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        snippets.append(text)

    snippets: list[str] = []
    seen: set[str] = set()

    scalar_candidates = (payload.get("topic_overview"), payload.get("overview"))
    for candidate in scalar_candidates:
        add_snippet(candidate)

    list_fields = (
        "summary_paragraphs",
        "summary_bullets",
        "highlights",
        "key_points_to_remember",
        "key_ideas",
        "answered_questions",
    )
    for field in list_fields:
        value = payload.get(field)
        if isinstance(value, list | tuple | set):
            for item in value:
                add_snippet(item)
        elif value is not None:
            add_snippet(value)

    questions_answered = payload.get("questions_answered")
    if isinstance(questions_answered, list):
        for entry in questions_answered:
            if isinstance(entry, dict):
                question = str(entry.get("question", "")).strip()
                answer = str(entry.get("answer", "")).strip()
                if question and answer:
                    add_snippet(f"{question}: {answer}")
                elif question:
                    add_snippet(question)
                elif answer:
                    add_snippet(answer)
            else:
                add_snippet(entry)

    extractive_quotes = payload.get("extractive_quotes")
    if isinstance(extractive_quotes, list):
        for quote in extractive_quotes:
            if isinstance(quote, dict):
                add_snippet(quote.get("text"))
            else:
                add_snippet(quote)

    insights = payload.get("insights")
    if isinstance(insights, dict):
        add_snippet(insights.get("topic_overview"))
        add_snippet(insights.get("caution"))
        new_facts = insights.get("new_facts")
        if isinstance(new_facts, list):
            for fact in new_facts:
                if isinstance(fact, dict):
                    fact_text = str(fact.get("fact", "")).strip()
                    why = str(fact.get("why_it_matters", "")).strip()
                    if fact_text and why:
                        add_snippet(f"{fact_text} -- {why}")
                    else:
                        add_snippet(fact_text or why)
                else:
                    add_snippet(fact)

    if not snippets:
        return None

    combined = " ".join(snippets[:6]).strip()
    return combined or None


def enrich_tldr_from_payload(base_text: str, payload: SummaryJSON) -> str:
    """Expand a TL;DR when it mirrors the 1000-char summary."""

    def add_segment(text: str) -> None:
        cleaned = str(text).strip()
        if not cleaned:
            return
        normalized = normalize_whitespace(cleaned).lower()
        if normalized in seen:
            return
        seen.add(normalized)
        segments.append(cleaned)

    segments: list[str] = []
    seen: set[str] = set()

    add_segment(base_text)

    key_ideas = clean_string_list(payload.get("key_ideas"), limit=6)
    if key_ideas:
        add_segment(f"Key ideas: {'; '.join(key_ideas)}.")

    highlights = clean_string_list(payload.get("highlights"), limit=5)
    if highlights:
        add_segment(f"Highlights: {'; '.join(highlights)}.")

    stats_parts: list[str] = []
    for stat in payload.get("key_stats") or []:
        if not isinstance(stat, dict):
            continue
        label = str(stat.get("label", "")).strip()
        value = stat.get("value")
        if not label or not is_numeric(value):
            continue
        unit_raw = stat.get("unit")
        unit = str(unit_raw).strip() if unit_raw is not None else ""
        unit_part = f" {unit}" if unit else ""
        stats_parts.append(f"{label}: {value}{unit_part}")
    if stats_parts:
        add_segment(f"Key stats: {'; '.join(stats_parts)}.")

    answered = payload.get("answered_questions")
    if isinstance(answered, list):
        questions: list[str] = []
        for qa in answered:
            if isinstance(qa, dict):
                question = str(qa.get("question", "")).strip()
                answer = str(qa.get("answer", "")).strip()
                if question and answer:
                    questions.append(f"{question} -- {answer}")
                elif question:
                    questions.append(question)
            elif isinstance(qa, str) and qa.strip():
                questions.append(qa.strip())
        if questions:
            deduped = _dedupe_case_insensitive(questions)
            add_segment(f"Questions answered: {'; '.join(deduped)}.")

    insights = payload.get("insights")
    if isinstance(insights, dict):
        topic_overview = str(insights.get("topic_overview", "")).strip()
        if topic_overview:
            add_segment(topic_overview)
        caution_raw = insights.get("caution")
        caution = str(caution_raw).strip() if caution_raw is not None else ""
        if caution:
            add_segment(f"Caution: {caution}")

    fallback = summary_fallback_from_supporting_fields(payload)
    if fallback:
        add_segment(fallback)

    enriched = " ".join(segments).strip()
    if not enriched:
        return base_text
    return _cap_text(enriched, 2000)
