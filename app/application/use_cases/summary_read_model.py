"""Application use case for summary read/write operations used by API adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.application.ports import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
        SummaryRepositoryPort,
    )


class SummaryReadModelUseCase:
    """Orchestrates summary operations for presentation adapters.

    This keeps API routers free from direct repository calls.
    """

    def __init__(
        self,
        summary_repository: SummaryRepositoryPort,
        request_repository: RequestRepositoryPort,
        crawl_result_repository: CrawlResultRepositoryPort,
        llm_repository: LLMRepositoryPort,
    ) -> None:
        self._summary_repo = summary_repository
        self._request_repo = request_repository
        self._crawl_repo = crawl_result_repository
        self._llm_repo = llm_repository

    async def get_user_summaries(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        is_read: bool | None = None,
        is_favorited: bool | None = None,
        lang: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        sort: str = "created_at_desc",
    ) -> tuple[list[dict[str, Any]], int, int]:
        return await self._summary_repo.async_get_user_summaries(
            user_id=user_id,
            limit=limit,
            offset=offset,
            is_read=is_read,
            is_favorited=is_favorited,
            lang=lang,
            start_date=start_date,
            end_date=end_date,
            sort=sort,
        )

    async def get_summary_by_id_for_user(
        self, user_id: int, summary_id: int
    ) -> dict[str, Any] | None:
        summary = await self._summary_repo.async_get_summary_by_id(summary_id)
        if not summary:
            return None
        if summary.get("user_id") != user_id or summary.get("is_deleted"):
            return None
        return summary

    async def get_summary_id_by_url_for_user(self, user_id: int, url: str) -> int | None:
        request_id = await self._request_repo.async_get_request_id_by_url_with_summary(
            user_id=user_id,
            url=url,
        )
        if not request_id:
            return None
        return await self._summary_repo.async_get_summary_id_by_request(request_id)

    async def get_request_by_id(self, request_id: int) -> dict[str, Any] | None:
        return await self._request_repo.async_get_request_by_id(request_id)

    async def get_crawl_result_by_request(self, request_id: int) -> dict[str, Any] | None:
        return await self._crawl_repo.async_get_crawl_result_by_request(request_id)

    async def get_llm_calls_by_request(self, request_id: int) -> list[dict[str, Any]]:
        return await self._llm_repo.async_get_llm_calls_by_request(request_id)

    async def get_summary_context_for_user(
        self, user_id: int, summary_id: int
    ) -> dict[str, Any] | None:
        summary = await self.get_summary_by_id_for_user(user_id=user_id, summary_id=summary_id)
        if not summary:
            return None

        request_data = summary.get("request") or {}
        if isinstance(request_data, int):
            request_id = request_data
            request_data = await self._request_repo.async_get_request_by_id(request_id) or {}
        else:
            request_id = request_data.get("id", summary.get("request_id"))
            if request_id is None:
                request_id = summary.get("request_id")
                if request_id is not None:
                    request_data = (
                        await self._request_repo.async_get_request_by_id(request_id) or {}
                    )

        if request_id is None:
            return None

        request_id_int = int(request_id)
        crawl_result = await self._crawl_repo.async_get_crawl_result_by_request(request_id_int)
        llm_calls = await self._llm_repo.async_get_llm_calls_by_request(request_id_int)
        return {
            "summary": summary,
            "request": request_data,
            "request_id": request_id_int,
            "crawl_result": crawl_result,
            "llm_calls": llm_calls,
        }

    async def update_summary(
        self,
        user_id: int,
        summary_id: int,
        is_read: bool | None = None,
    ) -> dict[str, Any] | None:
        summary = await self.get_summary_by_id_for_user(user_id=user_id, summary_id=summary_id)
        if not summary:
            return None

        if is_read is not None:
            if is_read:
                await self._summary_repo.async_mark_summary_as_read(summary_id)
            else:
                await self._summary_repo.async_mark_summary_as_unread(summary_id)

        return await self._summary_repo.async_get_summary_by_id(summary_id)

    async def soft_delete_summary(self, user_id: int, summary_id: int) -> bool:
        summary = await self.get_summary_by_id_for_user(user_id=user_id, summary_id=summary_id)
        if not summary:
            return False

        await self._summary_repo.async_soft_delete_summary(summary_id)
        return True

    async def toggle_favorite(self, user_id: int, summary_id: int) -> bool | None:
        summary = await self.get_summary_by_id_for_user(user_id=user_id, summary_id=summary_id)
        if not summary:
            return None
        return await self._summary_repo.async_toggle_favorite(summary_id)
