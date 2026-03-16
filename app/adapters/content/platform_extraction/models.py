"""Shared request and result models for platform extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.core.progress_tracker import ProgressTracker

PlatformExtractionMode = Literal["interactive", "pure"]


@dataclass(slots=True)
class PlatformExtractionRequest:
    """Normalized request envelope for platform-specific extraction."""

    message: Any
    url_text: str
    normalized_url: str
    correlation_id: str | None = None
    interaction_id: int | None = None
    silent: bool = False
    progress_tracker: ProgressTracker | None = None
    request_id_override: int | None = None
    mode: PlatformExtractionMode = "interactive"


@dataclass(slots=True)
class PlatformExtractionResult:
    """Unified result for platform-specific extraction."""

    platform: str
    request_id: int | None
    content_text: str
    content_source: str
    detected_lang: str
    title: str | None = None
    images: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
