"""Record collection helpers for sync flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.api.models.responses import SyncEntityEnvelope

    from .serializer import SyncEnvelopeSerializer


class SyncAuxReadPort(Protocol):
    def get_highlights_for_user(self, user_id: int) -> list[dict[str, Any]]: ...

    def get_tags_for_user(self, user_id: int) -> list[dict[str, Any]]: ...

    def get_summary_tags_for_user(self, user_id: int) -> list[dict[str, Any]]: ...


class SyncRecordCollector:
    def __init__(
        self,
        *,
        user_repository: Any,
        request_repository: Any,
        summary_repository: Any,
        crawl_result_repository: Any,
        llm_repository: Any,
        aux_read_port: SyncAuxReadPort,
        serializer: SyncEnvelopeSerializer,
    ) -> None:
        self._user_repo = user_repository
        self._request_repo = request_repository
        self._summary_repo = summary_repository
        self._crawl_repo = crawl_result_repository
        self._llm_repo = llm_repository
        self._aux_read_port = aux_read_port
        self._serializer = serializer

    async def collect_records(self, user_id: int) -> list[SyncEntityEnvelope]:
        records: list[SyncEntityEnvelope] = []

        user = await self._user_repo.async_get_user_by_telegram_id(user_id)
        if user:
            records.append(self._serializer.serialize_user(user))

        requests = await self._request_repo.async_get_all_for_user(user_id)
        for request in requests:
            records.append(self._serializer.serialize_request(request))

        summaries = await self._summary_repo.async_get_all_for_user(user_id)
        for summary in summaries:
            records.append(self._serializer.serialize_summary(summary))

        crawl_results = await self._crawl_repo.async_get_all_for_user(user_id)
        for crawl in crawl_results:
            records.append(self._serializer.serialize_crawl_result(crawl))

        llm_calls = await self._llm_repo.async_get_all_for_user(user_id)
        for call in llm_calls:
            records.append(self._serializer.serialize_llm_call(call))

        highlights = self._aux_read_port.get_highlights_for_user(user_id)
        for highlight in highlights:
            records.append(self._serializer.serialize_highlight(highlight))

        tags = self._aux_read_port.get_tags_for_user(user_id)
        for tag in tags:
            records.append(self._serializer.serialize_tag(tag))

        summary_tags = self._aux_read_port.get_summary_tags_for_user(user_id)
        for st in summary_tags:
            records.append(self._serializer.serialize_summary_tag(st))

        records.sort(key=lambda r: (r.server_version, str(r.id)))
        return records

    @staticmethod
    def paginate_records(
        records: Iterable[SyncEntityEnvelope], since: int, limit: int
    ) -> tuple[list[SyncEntityEnvelope], bool, int | None]:
        filtered = [rec for rec in records if rec.server_version > since]
        page = filtered[:limit]
        has_more = len(filtered) > limit
        next_since = page[-1].server_version if page else since
        return page, has_more, next_since
