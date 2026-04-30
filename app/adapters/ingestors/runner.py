"""Persistence runner for pluggable source ingestors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.application.ports.source_ingestors import AuthSourceError, SourceIngester
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.application.ports.signal_sources import SignalSourceRepositoryPort

logger = get_logger(__name__)

MAX_FETCH_ERRORS = 10
BASE_BACKOFF_SECONDS = 300
AUTH_MAX_FETCH_ERRORS = 1


@dataclass(slots=True, frozen=True)
class SourceIngestionRunnerStats:
    enabled: int
    sources: int
    items: int
    errors: int
    skipped: int

    def to_dict(self) -> dict[str, int]:
        return {
            "enabled": self.enabled,
            "sources": self.sources,
            "items": self.items,
            "errors": self.errors,
            "skipped": self.skipped,
        }


class SourceIngestionRunner:
    """Run configured source ingestors and persist generic feed items."""

    def __init__(
        self,
        *,
        repository: SignalSourceRepositoryPort,
        ingesters: Iterable[SourceIngester],
        subscriber_user_ids: Iterable[int],
    ) -> None:
        self._repository = repository
        self._ingesters = list(ingesters)
        self._subscriber_user_ids = [int(user_id) for user_id in subscriber_user_ids]

    async def run_once(self) -> dict[str, int]:
        enabled_ingesters = [ingester for ingester in self._ingesters if ingester.is_enabled()]
        sources = 0
        items = 0
        errors = 0
        skipped = len(self._ingesters) - len(enabled_ingesters)

        for ingester in enabled_ingesters:
            source_id: int | None = None
            try:
                result = await ingester.fetch()
                source = await self._repository.async_upsert_source(
                    kind=result.source.kind,
                    external_id=result.source.external_id,
                    url=result.source.url,
                    title=result.source.title,
                    description=result.source.description,
                    site_url=result.source.site_url,
                    metadata={**result.source.metadata, **result.metadata},
                )
                source_id = int(source["id"])
                sources += 1
                for user_id in self._subscriber_user_ids:
                    await self._repository.async_subscribe(user_id=user_id, source_id=source_id)
                if result.not_modified:
                    await self._repository.async_record_source_fetch_success(source_id)
                    continue
                for item in result.items:
                    await self._repository.async_upsert_feed_item(
                        source_id=source_id,
                        external_id=item.external_id,
                        canonical_url=item.canonical_url,
                        title=item.title,
                        content_text=item.content_text,
                        author=item.author,
                        published_at=item.published_at,
                        engagement=item.engagement,
                        metadata=item.metadata,
                    )
                    items += 1
                await self._repository.async_record_source_fetch_success(source_id)
            except Exception as exc:
                errors += 1
                if source_id is not None:
                    await self._repository.async_record_source_fetch_error(
                        source_id=source_id,
                        error=str(exc),
                        max_errors=AUTH_MAX_FETCH_ERRORS
                        if isinstance(exc, AuthSourceError)
                        else MAX_FETCH_ERRORS,
                        base_backoff_seconds=BASE_BACKOFF_SECONDS,
                    )
                logger.warning(
                    "source_ingester_failed",
                    extra={"ingester": getattr(ingester, "name", "unknown"), "error": str(exc)},
                    exc_info=True,
                )

        return SourceIngestionRunnerStats(
            enabled=len(enabled_ingesters),
            sources=sources,
            items=items,
            errors=errors,
            skipped=skipped,
        ).to_dict()
