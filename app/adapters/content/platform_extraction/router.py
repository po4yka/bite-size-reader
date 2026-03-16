"""Lazy router for platform-specific extraction handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.content.platform_extraction.models import (
        PlatformExtractionRequest,
        PlatformExtractionResult,
    )
    from app.adapters.content.platform_extraction.protocol import PlatformExtractor


class PlatformExtractionRouter:
    """Route platform URLs to lazily-created extractors."""

    def __init__(self) -> None:
        self._entries: list[tuple[Callable[[str], bool], Callable[[], PlatformExtractor]]] = []
        self._instances: dict[int, PlatformExtractor] = {}

    def register(
        self,
        *,
        predicate: Callable[[str], bool],
        factory: Callable[[], PlatformExtractor],
    ) -> None:
        self._entries.append((predicate, factory))

    async def extract(
        self,
        request: PlatformExtractionRequest,
    ) -> PlatformExtractionResult | None:
        for index, (predicate, factory) in enumerate(self._entries):
            if not predicate(request.normalized_url):
                continue
            extractor = self._instances.get(index)
            if extractor is None:
                extractor = factory()
                self._instances[index] = extractor
            if extractor.supports(request.normalized_url):
                return await extractor.extract(request)
        return None
