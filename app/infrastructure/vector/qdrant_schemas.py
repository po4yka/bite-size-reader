"""Filter translation from generic query params to Qdrant Filter objects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue


class QdrantQueryFilters(BaseModel):
    """Validated query filters translated to a ``qdrant_client.models.Filter``.

    Mirrors ``ChromaQueryFilters`` field-for-field so that callers can swap
    filter builders without changing their own code.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    environment: str
    user_scope: str
    language: str | None = None
    tags: list[str] = Field(default_factory=list)
    request_id: int | None = Field(default=None, ge=0)
    summary_id: int | None = Field(default=None, ge=0)
    user_id: int | None = Field(default=None, ge=1)

    @field_validator("environment", "user_scope", mode="before")
    @classmethod
    def _sanitize_scope(cls, value: Any, info: ValidationInfo) -> str:
        cleaned = "".join(ch for ch in str(value or "") if ch.isalnum() or ch in {"-", "_"}).lower()
        if not cleaned:
            msg = f"{info.field_name} cannot be empty"
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
            cleaned = str(value).strip().lstrip("#")
            return [cleaned] if cleaned else []
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            cleaned = str(item).strip().lstrip("#")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                result.append(cleaned)
            if len(result) >= 64:
                break
        return result

    def to_filter(self) -> Filter:
        """Build a Qdrant ``Filter`` from the validated fields.

        Each tag must appear in the ``tags`` array (AND semantics —
        mirrors Chroma's ``$contains`` inside ``$and``).
        """
        must: list[Any] = [
            FieldCondition(key="environment", match=MatchValue(value=self.environment)),
            FieldCondition(key="user_scope", match=MatchValue(value=self.user_scope)),
        ]
        if self.language:
            must.append(FieldCondition(key="language", match=MatchValue(value=self.language)))
        if self.request_id is not None:
            must.append(FieldCondition(key="request_id", match=MatchValue(value=self.request_id)))
        if self.summary_id is not None:
            must.append(FieldCondition(key="summary_id", match=MatchValue(value=self.summary_id)))
        if self.user_id is not None:
            must.append(FieldCondition(key="user_id", match=MatchValue(value=self.user_id)))
        for tag in self.tags:
            # MatchAny(any=[tag]) → "tags array contains tag" (Qdrant keyword field)
            must.append(FieldCondition(key="tags", match=MatchAny(any=[tag])))
        return Filter(must=must)
