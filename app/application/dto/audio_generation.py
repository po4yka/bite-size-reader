"""DTOs for audio generation workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoredAudioFileDTO:
    file_path: str
    file_size_bytes: int


@dataclass(frozen=True, slots=True)
class AudioGenerationResult:
    summary_id: int
    status: str
    file_path: str | None = None
    file_size_bytes: int | None = None
    char_count: int | None = None
    latency_ms: int | None = None
    error: str | None = None
