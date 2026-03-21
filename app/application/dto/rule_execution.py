"""DTOs for rule evaluation and execution workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RuleEvaluationContextDTO:
    url: str = ""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    language: str = ""
    reading_time: int = 0
    source_type: str = ""
    content: str = ""
    summary_snapshot: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "tags": self.tags,
            "language": self.language,
            "reading_time": self.reading_time,
            "source_type": self.source_type,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class RuleActionResultDTO:
    type: str
    success: bool
    detail: str


@dataclass(frozen=True, slots=True)
class RuleExecutionResultDTO:
    rule_id: int
    matched: bool
    actions_taken: list[RuleActionResultDTO] = field(default_factory=list)
    error: str | None = None
