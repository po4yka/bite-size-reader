from __future__ import annotations

try:
    from pydantic import BaseModel, Field

    PydanticAvailable = True
except Exception:  # pragma: no cover - optional dependency
    PydanticAvailable = False


if PydanticAvailable:

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

    class SummaryModel(BaseModel):
        summary_250: str = Field(max_length=250)
        summary_1000: str = Field(max_length=1000)
        key_ideas: list[str] = Field(default_factory=list)
        topic_tags: list[str] = Field(default_factory=list)
        entities: Entities = Field(default_factory=Entities)
        estimated_reading_time_min: int = 0
        key_stats: list[KeyStat] = Field(default_factory=list)
        answered_questions: list[str] = Field(default_factory=list)
        readability: Readability = Field(default_factory=Readability)
        seo_keywords: list[str] = Field(default_factory=list)

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
