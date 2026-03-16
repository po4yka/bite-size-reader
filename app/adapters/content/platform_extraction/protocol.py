"""Protocol for platform-specific extractors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.adapters.content.platform_extraction.models import (
        PlatformExtractionRequest,
        PlatformExtractionResult,
    )


class PlatformExtractor(Protocol):
    """Contract for lazily-instantiated platform extractors."""

    def supports(self, normalized_url: str) -> bool:
        """Return whether this extractor handles the normalized URL."""

    async def extract(self, request: PlatformExtractionRequest) -> PlatformExtractionResult:
        """Extract platform-specific content for the request."""
