from __future__ import annotations

try:
    from pydantic import BaseModel, Field

    PydanticAvailable = True
except Exception:  # pragma: no cover - optional dependency
    BaseModel = object  # type: ignore

    def _field_stub(*a, **k):  # type: ignore
        return None

    Field = _field_stub  # type: ignore
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
