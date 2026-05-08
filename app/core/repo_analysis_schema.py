from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["CodePattern", "KeyConcept", "RepoAnalysis", "RepoAnalysisInput"]


class KeyConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(..., min_length=1, max_length=100)
    explanation: str = Field(..., min_length=1, max_length=300)


class CodePattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=400)


class RepoAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(..., min_length=10, max_length=500)
    tech_stack: list[str] = Field(..., max_length=20)
    architecture_summary: str = Field(..., min_length=20, max_length=1500)
    key_concepts: list[KeyConcept] = Field(..., max_length=15)
    code_patterns: list[CodePattern] = Field(default_factory=list, max_length=10)
    use_cases: list[str] = Field(..., max_length=10)
    target_audience: str = Field(..., min_length=5, max_length=300)
    maturity: Literal["prototype", "alpha", "beta", "stable", "mature", "abandoned"]
    key_dependencies: list[str] = Field(default_factory=list, max_length=15)
    hallucination_risk: Literal["low", "medium", "high"]
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("tech_stack", mode="before")
    @classmethod
    def _clean_tech_stack(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if isinstance(item, str) and item.strip()]
        if not cleaned:
            raise ValueError("tech_stack must contain at least one item")
        return cleaned

    @field_validator("use_cases", mode="before")
    @classmethod
    def _clean_use_cases(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if isinstance(item, str) and item.strip()]
        if not cleaned:
            raise ValueError("use_cases must contain at least one item")
        for item in cleaned:
            if len(item) > 200:
                raise ValueError(f"use_cases item exceeds 200 chars: {item[:50]!r}...")
        return cleaned

    @field_validator("key_concepts", mode="before")
    @classmethod
    def _require_key_concepts(cls, v: list[KeyConcept]) -> list[KeyConcept]:
        if not v:
            raise ValueError("key_concepts must contain at least one item")
        return v

    @field_validator("key_dependencies", mode="before")
    @classmethod
    def _clean_key_dependencies(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if isinstance(item, str) and item.strip()]
        for item in cleaned:
            if len(item) > 100:
                raise ValueError(f"key_dependencies item exceeds 100 chars: {item[:50]!r}...")
        return cleaned


class RepoAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    description: str | None = None
    topics: list[str] = Field(default_factory=list)
    primary_language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    license_spdx: str | None = None
    readme_excerpt: str | None = None
    default_branch: str | None = None
