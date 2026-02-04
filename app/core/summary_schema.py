from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Kept as a constant for backward compatibility with any code that imports it.
PydanticAvailable = True


# ---------------------------------------------------------------------------
# Helper utilities used by validators (duplicated from summary_contract to
# avoid circular imports -- these are tiny pure functions).
# ---------------------------------------------------------------------------


def _cap_text(text: str, limit: int) -> str:
    """Cap *text* to *limit* characters, trimming at a sentence boundary."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if not isinstance(limit, int) or limit <= 0:
        msg = "Limit must be a positive integer"
        raise ValueError(msg)
    if limit > 10000:
        msg = "Limit too large"
        raise ValueError(msg)
    if len(text) <= limit:
        return text
    snippet = text[:limit]
    for sep in (". ", "! ", "? ", "; ", ", "):
        idx = snippet.rfind(sep)
        if idx > 0:
            return snippet[: idx + len(sep)].strip()
    return snippet.strip()


def _hash_tagify(tags: list[str], max_tags: int = 10) -> list[str]:
    """Deduplicate tags, enforce ``#`` prefix, and cap count."""
    if not isinstance(tags, list):
        return []
    if not isinstance(max_tags, int) or max_tags <= 0 or max_tags > 100:
        max_tags = 10
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        if len(t) > 100:
            continue
        if any(char in t.lower() for char in ["<", ">", "script", "javascript"]):
            continue
        if not t.startswith("#"):
            t = f"#{t}"
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
        if len(result) >= max_tags:
            break
    return result


def _dedupe_case_insensitive(items: list[str]) -> list[str]:
    if not isinstance(items, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if not isinstance(it, str):
            continue
        key = it.strip().lower()
        if key and key not in seen:
            if len(key) > 500:
                continue
            if any(char in key for char in ["<", ">", "script", "javascript"]):
                continue
            seen.add(key)
            out.append(it.strip())
    return out


# ---------------------------------------------------------------------------
# Field-name normalization mapping (camelCase -> snake_case)
# ---------------------------------------------------------------------------

_FIELD_NAME_MAPPING: dict[str, str] = {
    "summary": "summary_1000",
    "summary250": "summary_250",
    "summary1000": "summary_1000",
    "keyideas": "key_ideas",
    "keyIdeas": "key_ideas",
    "topictags": "topic_tags",
    "topicTags": "topic_tags",
    "estimatedreadingtimemin": "estimated_reading_time_min",
    "estimatedReadingTimeMin": "estimated_reading_time_min",
    "keystats": "key_stats",
    "keyStats": "key_stats",
    "answeredquestions": "answered_questions",
    "answeredQuestions": "answered_questions",
    "seokeywords": "seo_keywords",
    "seoKeywords": "seo_keywords",
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
}


# ---------------------------------------------------------------------------
# Pydantic sub-models
# ---------------------------------------------------------------------------


class Entities(BaseModel):
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class Readability(BaseModel):
    method: str = Field(default="Flesch-Kincaid")
    score: float = 0.0
    level: str = Field(default="Unknown")


class KeyStat(BaseModel):
    label: str
    value: float
    unit: str | None = None
    source_excerpt: str | None = None


class Metadata(BaseModel):
    title: str | None = None
    canonical_url: str | None = None
    domain: str | None = None
    author: str | None = None
    published_at: str | None = None
    last_updated: str | None = None


class ExtractiveQuote(BaseModel):
    text: str
    source_span: str | None = None


class QuestionAnswer(BaseModel):
    question: str
    answer: str


class InsightFact(BaseModel):
    fact: str
    why_it_matters: str | None = None
    source_hint: str | None = None
    confidence: float | str | None = None


class Insights(BaseModel):
    topic_overview: str = Field(default="")
    new_facts: list[InsightFact] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    suggested_sources: list[str] = Field(default_factory=list)
    expansion_topics: list[str] = Field(default_factory=list)
    next_exploration: list[str] = Field(default_factory=list)
    caution: str | None = None


class TopicTaxonomy(BaseModel):
    label: str
    score: float = 0.0
    path: str | None = None


class ForwardedPostExtras(BaseModel):
    channel_id: int | None = None
    channel_title: str | None = None
    channel_username: str | None = None
    message_id: int | None = None
    post_datetime: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)


class SemanticChunk(BaseModel):
    text: str
    local_summary: str | None = None
    local_keywords: list[str] = Field(default_factory=list)
    article_id: str | None = None
    section: str | None = None
    language: str | None = None
    topics: list[str] = Field(default_factory=list)


class SourceType(str, Enum):
    """Content type classification."""

    NEWS = "news"
    BLOG = "blog"
    RESEARCH = "research"
    OPINION = "opinion"
    TUTORIAL = "tutorial"
    REFERENCE = "reference"


class TemporalFreshness(str, Enum):
    """Content timeliness classification."""

    BREAKING = "breaking"
    RECENT = "recent"
    EVERGREEN = "evergreen"


# ---------------------------------------------------------------------------
# Main summary model
# ---------------------------------------------------------------------------


class SummaryModel(BaseModel):
    summary_250: str = Field(default="", max_length=250)
    summary_1000: str = Field(default="", max_length=1000)
    tldr: str = Field(default="")
    key_ideas: list[str] = Field(default_factory=list)
    topic_tags: list[str] = Field(default_factory=list)
    entities: Entities = Field(default_factory=Entities)
    estimated_reading_time_min: int = 0
    key_stats: list[KeyStat] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    readability: Readability = Field(default_factory=Readability)
    seo_keywords: list[str] = Field(default_factory=list)
    query_expansion_keywords: list[str] = Field(default_factory=list)
    semantic_boosters: list[str] = Field(default_factory=list)
    semantic_chunks: list[SemanticChunk] = Field(default_factory=list)
    article_id: str | None = None

    # Classification fields
    source_type: Literal["news", "blog", "research", "opinion", "tutorial", "reference"] = Field(
        default="blog"
    )
    temporal_freshness: Literal["breaking", "recent", "evergreen"] = Field(default="evergreen")

    # New fields
    metadata: Metadata = Field(default_factory=Metadata)
    extractive_quotes: list[ExtractiveQuote] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    questions_answered: list[QuestionAnswer] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    topic_taxonomy: list[TopicTaxonomy] = Field(default_factory=list)
    hallucination_risk: str = Field(default="low")  # low/med/high
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    forwarded_post_extras: ForwardedPostExtras | None = None
    key_points_to_remember: list[str] = Field(default_factory=list)
    insights: Insights = Field(default_factory=Insights)

    # ------------------------------------------------------------------
    # model_validator: normalize field names and backfill summaries
    # ------------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def normalize_and_backfill(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # --- 1. Normalize field names (camelCase -> snake_case) ---
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            normalized_key = _FIELD_NAME_MAPPING.get(key, key)
            normalized[normalized_key] = value
        data = normalized

        # --- 2. Backfill summary fields ---
        tldr = str(data.get("tldr") or "").strip()
        s250 = str(data.get("summary_250") or "").strip()
        s1000 = str(data.get("summary_1000") or "").strip()

        if not s1000 and "summary" in data:
            s1000 = str(data.get("summary") or "").strip()

        if not tldr and s1000:
            tldr = s1000
        if not s1000 and tldr:
            s1000 = tldr
        if not s250 and s1000:
            s250 = _cap_text(s1000, 250)
        if not s250 and tldr:
            s250 = _cap_text(tldr, 250)
        if not s1000 and s250:
            s1000 = s250
        if not tldr:
            tldr = s1000 or s250

        data["summary_250"] = s250
        data["summary_1000"] = s1000
        data["tldr"] = tldr

        return data

    # ------------------------------------------------------------------
    # field_validators
    # ------------------------------------------------------------------

    @field_validator("summary_250", mode="before")
    @classmethod
    def cap_summary_250(cls, v: Any) -> str:
        text = str(v).strip() if v is not None else ""
        return _cap_text(text, 250)

    @field_validator("summary_1000", mode="before")
    @classmethod
    def cap_summary_1000(cls, v: Any) -> str:
        text = str(v).strip() if v is not None else ""
        return _cap_text(text, 1000)

    @field_validator("topic_tags", mode="before")
    @classmethod
    def normalize_topic_tags(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return _hash_tagify([str(x) for x in v])

    @field_validator("estimated_reading_time_min", mode="before")
    @classmethod
    def coerce_reading_time(cls, v: Any) -> int:
        if v is None:
            return 0
        try:
            return int(v)
        except (ValueError, TypeError):
            return 0

    @field_validator("key_stats", mode="before")
    @classmethod
    def filter_key_stats(cls, v: Any) -> list[dict[str, Any]]:
        if not isinstance(v, list):
            return []
        result: list[dict[str, Any]] = []
        for item in v:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            try:
                value = float(item.get("value"))
            except (TypeError, ValueError):
                continue
            unit = item.get("unit")
            source_excerpt = item.get("source_excerpt")
            result.append(
                {
                    "label": label,
                    "value": value,
                    "unit": str(unit) if unit is not None else None,
                    "source_excerpt": str(source_excerpt) if source_excerpt is not None else None,
                }
            )
        return result

    @field_validator("hallucination_risk", mode="before")
    @classmethod
    def constrain_hallucination_risk(cls, v: Any) -> str:
        val = str(v).strip().lower() if v is not None else "low"
        return val if val in {"low", "med", "high"} else "low"

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        if v is None:
            return 1.0
        try:
            val = float(v)
        except (TypeError, ValueError):
            return 1.0
        return max(0.0, min(1.0, val))

    @field_validator("source_type", mode="before")
    @classmethod
    def default_source_type(cls, v: Any) -> str:
        valid = {"news", "blog", "research", "opinion", "tutorial", "reference"}
        val = str(v).strip().lower() if v is not None else "blog"
        return val if val in valid else "blog"

    @field_validator("temporal_freshness", mode="before")
    @classmethod
    def default_temporal_freshness(cls, v: Any) -> str:
        valid = {"breaking", "recent", "evergreen"}
        val = str(v).strip().lower() if v is not None else "evergreen"
        return val if val in valid else "evergreen"
