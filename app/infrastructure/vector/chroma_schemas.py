from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChromaMetadata(BaseModel):
    """Validated metadata schema for Chroma upserts."""

    model_config = ConfigDict(extra="forbid", validate_default=True, str_strip_whitespace=True)

    request_id: int = Field(..., ge=0)
    summary_id: int = Field(..., ge=0)
    user_scope: str = Field(...)
    environment: str = Field(...)
    text: str = Field(..., min_length=1)
    language: str | None = None
    url: str | None = None
    title: str | None = None
    source: str | None = None
    published_at: str | None = None
    window_id: str | None = None
    window_index: int | None = Field(default=None, ge=0)
    chunk_id: str | None = None
    neighbor_chunk_ids: list[str] = Field(default_factory=list)
    created_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    semantic_boosters: list[str] = Field(default_factory=list)
    local_keywords: list[str] = Field(default_factory=list)
    local_summary: str | None = None
    query_expansion_keywords: list[str] = Field(default_factory=list)
    section: str | None = None

    @field_validator("user_scope", "environment", mode="before")
    @classmethod
    def _sanitize_scope(cls, value: Any) -> str:
        cleaned = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_"}).lower()
        if not cleaned:
            msg = "environment/user_scope cannot be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            msg = "text is required for Chroma metadata"
            raise ValueError(msg)
        if len(text) > 20000:
            text = text[:20000]
        return text

    @field_validator(
        "tags",
        "topics",
        "semantic_boosters",
        "local_keywords",
        "neighbor_chunk_ids",
        "query_expansion_keywords",
        mode="before",
    )
    @classmethod
    def _clean_list(cls, value: Any) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, set | tuple):
            value = list(value)
        if not isinstance(value, list):
            return [str(value).strip()] if str(value).strip() else []
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
            if len(result) >= 128:
                break
        return result


class ChromaQueryFilters(BaseModel):
    """Validated query filters for Chroma queries."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    environment: str
    user_scope: str
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    request_id: int | None = Field(default=None, ge=0)
    summary_id: int | None = Field(default=None, ge=0)

    @field_validator("environment", "user_scope", mode="before")
    @classmethod
    def _sanitize_scope(cls, value: Any) -> str:
        cleaned = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_"}).lower()
        if not cleaned:
            msg = "environment/user_scope cannot be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("tags", mode="before")
    @classmethod
    def _clean_tags(cls, value: Any) -> list[str]:
        if value in (None, "", []):
            return []
        if isinstance(value, set | tuple):
            value = list(value)
        if not isinstance(value, list):
            return [str(value).strip()] if str(value).strip() else []
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
            if len(result) >= 64:
                break
        return result

    def to_where(self) -> dict[str, Any]:
        where: dict[str, Any] = {
            "environment": self.environment,
            "user_scope": self.user_scope,
        }
        if self.language:
            where["language"] = self.language
        if self.request_id is not None:
            where["request_id"] = self.request_id
        if self.summary_id is not None:
            where["summary_id"] = self.summary_id
        if self.tags:
            where["$and"] = [{"tags": {"$contains": tag}} for tag in self.tags]
        return where
