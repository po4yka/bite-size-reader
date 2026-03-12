"""ElevenLabs TTS API exceptions."""

from __future__ import annotations


class ElevenLabsError(Exception):
    """Base exception for ElevenLabs operations."""


class ElevenLabsAPIError(ElevenLabsError):
    """HTTP API error from ElevenLabs."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ElevenLabsRateLimitError(ElevenLabsAPIError):
    """Rate limit (429) from ElevenLabs API."""


class ElevenLabsQuotaExceededError(ElevenLabsAPIError):
    """Character quota exceeded."""
