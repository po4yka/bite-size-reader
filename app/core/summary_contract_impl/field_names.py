from __future__ import annotations

from typing import Any

FIELD_NAME_MAPPING: dict[str, str] = {
    "summary": "summary_1000",
    "summary250": "summary_250",
    "summary1000": "summary_1000",
    "summary_250": "summary_250",
    "summary_1000": "summary_1000",
    "keyideas": "key_ideas",
    "keyIdeas": "key_ideas",
    "key_ideas": "key_ideas",
    "topictags": "topic_tags",
    "topicTags": "topic_tags",
    "topic_tags": "topic_tags",
    "estimatedreadingtimemin": "estimated_reading_time_min",
    "estimatedReadingTimeMin": "estimated_reading_time_min",
    "estimated_reading_time_min": "estimated_reading_time_min",
    "keystats": "key_stats",
    "keyStats": "key_stats",
    "key_stats": "key_stats",
    "answeredquestions": "answered_questions",
    "answeredQuestions": "answered_questions",
    "answered_questions": "answered_questions",
    "seokeywords": "seo_keywords",
    "seoKeywords": "seo_keywords",
    "seo_keywords": "seo_keywords",
    "extractivequotes": "extractive_quotes",
    "extractiveQuotes": "extractive_quotes",
    "questionsanswered": "questions_answered",
    "questionsAnswered": "questions_answered",
    "topictaxonomy": "topic_taxonomy",
    "topicTaxonomy": "topic_taxonomy",
    "hallucinationrisk": "hallucination_risk",
    "hallucinationRisk": "hallucination_risk",
    "forwardedpostextras": "forwarded_post_extras",
    "forwardedPostExtras": "forwarded_post_extras",
    "keypointstoremember": "key_points_to_remember",
    "keyPointsToRemember": "key_points_to_remember",
    "tldrRu": "tldr_ru",
    "tldr_ru": "tldr_ru",
}


def normalize_field_names(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize field names from camelCase to snake_case."""
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = FIELD_NAME_MAPPING.get(key, key)
        normalized[normalized_key] = value
    return normalized
