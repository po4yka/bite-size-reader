"""Sync service compatibility facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.api.models.responses import (
    DeltaSyncResponseData,
    FullSyncResponseData,
    PaginationInfo,
    SyncApplyItemResult,
    SyncApplyResponseData,
    SyncEntityEnvelope,
    SyncSessionData,
)
from app.api.services.sync import (
    FallbackSyncSessionStore,
    InMemorySyncSessionStore,
    RedisSyncSessionStore,
    SyncApplyService,
    SyncEnvelopeSerializer,
    SyncFacade,
    SyncRecordCollector,
)
from app.infrastructure.redis import get_redis

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.api.models.requests import SyncApplyItem
    from app.api.services.sync.collector import SyncAuxReadPort
    from app.api.services.sync.session_store import SyncSessionStorePort
    from app.application.ports.requests import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
    )
    from app.application.ports.summaries import SummaryRepositoryPort
    from app.application.ports.users import UserRepositoryPort
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

else:

    class SyncAuxReadPort:  # pragma: no cover - runtime fallback for typing only
        pass


class _NullRepository:
    async def async_get_max_server_version(self, _user_id: int) -> int:
        return 0

    async def async_get_user_by_telegram_id(self, _user_id: int) -> dict[str, Any] | None:
        return None

    async def async_get_all_for_user(self, _user_id: int) -> list[dict[str, Any]]:
        return []

    async def async_get_summary_for_sync_apply(
        self, _summary_id: int, _user_id: int
    ) -> dict[str, Any] | None:
        return None

    async def async_apply_sync_change(self, *_args: Any, **_kwargs: Any) -> int:
        return 0


class _NullSyncAuxReadPort:
    async def get_highlights_for_user(self, _user_id: int) -> list[dict[str, Any]]:
        return []

    async def get_tags_for_user(self, _user_id: int) -> list[dict[str, Any]]:
        return []

    async def get_summary_tags_for_user(self, _user_id: int) -> list[dict[str, Any]]:
        return []


class SyncService:
    """Sync protocol service implementing sessions, retrieval, and apply."""

    def __init__(
        self,
        cfg: AppConfig,
        session_manager: DatabaseSessionManager,
        *,
        user_repository: UserRepositoryPort | None = None,
        request_repository: RequestRepositoryPort | None = None,
        summary_repository: SummaryRepositoryPort | None = None,
        crawl_result_repository: CrawlResultRepositoryPort | None = None,
        llm_repository: LLMRepositoryPort | None = None,
        session_store: SyncSessionStorePort | None = None,
        aux_read_port: SyncAuxReadPort | None = None,
        record_collector: SyncRecordCollector | None = None,
        envelope_serializer: SyncEnvelopeSerializer | None = None,
        apply_service: SyncApplyService | None = None,
    ) -> None:
        self.cfg = cfg
        self._session_manager = session_manager
        self._user_repo = user_repository or _NullRepository()
        self._request_repo = request_repository or _NullRepository()
        self._summary_repo = summary_repository or _NullRepository()
        self._crawl_repo = crawl_result_repository or _NullRepository()
        self._llm_repo = llm_repository or _NullRepository()

        self._serializer = envelope_serializer or SyncEnvelopeSerializer()
        self._fallback_store = InMemorySyncSessionStore()
        self._session_store = session_store or FallbackSyncSessionStore(
            redis_store=RedisSyncSessionStore(
                cfg,
                get_redis_func=lambda current_cfg: get_redis(current_cfg),
            ),
            fallback_store=self._fallback_store,
        )
        self._aux_read_port = aux_read_port or _NullSyncAuxReadPort()
        self._collector = record_collector or SyncRecordCollector(
            user_repository=self._user_repo,
            request_repository=self._request_repo,
            summary_repository=self._summary_repo,
            crawl_result_repository=self._crawl_repo,
            llm_repository=self._llm_repo,
            aux_read_port=self._aux_read_port,
            serializer=self._serializer,
        )
        self._apply_service = apply_service or SyncApplyService(
            summary_repository=self._summary_repo,
            serializer=self._serializer,
        )
        self._facade = SyncFacade(
            cfg=cfg,
            session_store=self._session_store,
            collector=self._collector,
            apply_service=self._apply_service,
            user_repository=self._user_repo,
            request_repository=self._request_repo,
            summary_repository=self._summary_repo,
            crawl_result_repository=self._crawl_repo,
            llm_repository=self._llm_repo,
        )
        self._sync_sessions = self._fallback_store._sessions

    @property
    def _redis_warning_logged(self) -> bool:
        return getattr(self._session_store, "_redis_warning_logged", False)

    @_redis_warning_logged.setter
    def _redis_warning_logged(self, value: bool) -> None:
        if hasattr(self._session_store, "_redis_warning_logged"):
            self._session_store._redis_warning_logged = value

    async def get_max_server_version(self, user_id: int) -> int:
        return await self._facade.get_max_server_version(user_id)

    def _resolve_limit(self, requested: int | None) -> int:
        return self._facade._resolve_limit(requested)

    async def _store_session(self, payload: dict[str, Any]) -> None:
        await self._facade._store_session(payload)

    async def _load_session(
        self, session_id: str, user_id: int, client_id: str | None
    ) -> dict[str, Any]:
        return await self._facade._load_session(session_id, user_id, client_id)

    async def start_session(
        self, *, user_id: int, client_id: str | None, limit: int | None
    ) -> SyncSessionData:
        import uuid
        from datetime import datetime, timedelta

        from app.core.time_utils import UTC

        resolved = self._resolve_limit(limit)
        session_id = f"sync-{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=self.cfg.sync.expiry_hours)
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "client_id": client_id,
            "chunk_limit": resolved,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "next_since": 0,
        }
        await self._store_session(payload)
        return SyncSessionData(
            session_id=session_id,
            expires_at=str(payload["expires_at"]),
            default_limit=self.cfg.sync.default_limit,
            max_limit=self.cfg.sync.max_limit,
            last_issued_since=0,
        )

    def _coerce_iso(self, dt_value: Any) -> str:
        return self._serializer._coerce_iso(dt_value)

    def _serialize_request(self, request: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_request(request)

    def _serialize_summary(self, summary: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_summary(summary)

    def _serialize_crawl_result(self, crawl: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_crawl_result(crawl)

    def _serialize_llm_call(self, call: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_llm_call(call)

    def _serialize_highlight(self, highlight: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_highlight(highlight)

    def _serialize_user(self, user: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_user(user)

    def _serialize_tag(self, tag: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_tag(tag)

    def _serialize_summary_tag(self, st: dict[str, Any]) -> SyncEntityEnvelope:
        return self._serializer.serialize_summary_tag(st)

    async def _get_highlights_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return await self._aux_read_port.get_highlights_for_user(user_id)

    async def _get_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return await self._aux_read_port.get_tags_for_user(user_id)

    async def _get_summary_tags_for_user(self, user_id: int) -> list[dict[str, Any]]:
        return await self._aux_read_port.get_summary_tags_for_user(user_id)

    async def _collect_records(self, user_id: int) -> list[SyncEntityEnvelope]:
        records: list[SyncEntityEnvelope] = []

        user = await self._user_repo.async_get_user_by_telegram_id(user_id)
        if user:
            records.append(self._serialize_user(user))

        requests = await self._request_repo.async_get_all_for_user(user_id)
        for request in requests:
            records.append(self._serialize_request(request))

        summaries = await self._summary_repo.async_get_all_for_user(user_id)
        for summary in summaries:
            records.append(self._serialize_summary(summary))

        crawl_results = await self._crawl_repo.async_get_all_for_user(user_id)
        for crawl in crawl_results:
            records.append(self._serialize_crawl_result(crawl))

        llm_calls = await self._llm_repo.async_get_all_for_user(user_id)
        for call in llm_calls:
            records.append(self._serialize_llm_call(call))

        for highlight in await self._get_highlights_for_user(user_id):
            records.append(self._serialize_highlight(highlight))

        for tag in await self._get_tags_for_user(user_id):
            records.append(self._serialize_tag(tag))

        for st in await self._get_summary_tags_for_user(user_id):
            records.append(self._serialize_summary_tag(st))

        records.sort(key=lambda r: (r.server_version, str(r.id)))
        return records

    def _paginate_records(
        self, records: Iterable[SyncEntityEnvelope], since: int, limit: int
    ) -> tuple[list[SyncEntityEnvelope], bool, int | None]:
        return self._collector.paginate_records(records, since, limit)

    async def get_full(
        self, *, session_id: str, user_id: int, client_id: str | None, limit: int | None
    ) -> FullSyncResponseData:
        session = await self._load_session(session_id, user_id, client_id)
        resolved_limit = self._resolve_limit(limit or session.get("chunk_limit"))
        records = await self._collect_records(user_id)
        page, has_more, next_since = self._paginate_records(records, since=0, limit=resolved_limit)
        return self._build_full(session_id, page, has_more, next_since, resolved_limit)

    async def get_delta(
        self, *, session_id: str, user_id: int, client_id: str | None, since: int, limit: int | None
    ) -> DeltaSyncResponseData:
        session = await self._load_session(session_id, user_id, client_id)
        resolved_limit = self._resolve_limit(limit or session.get("chunk_limit"))
        records = await self._collect_records(user_id)
        page, has_more, next_since = self._paginate_records(
            records, since=since, limit=resolved_limit
        )
        return self._build_delta(session_id, since, page, has_more, next_since, resolved_limit)

    def _build_full(
        self,
        session_id: str,
        records: list[SyncEntityEnvelope],
        has_more: bool,
        next_since: int | None,
        limit: int,
    ) -> FullSyncResponseData:
        pagination = PaginationInfo(
            total=len(records),
            limit=limit,
            offset=0,
            has_more=has_more,
        )
        return FullSyncResponseData(
            session_id=session_id,
            has_more=has_more,
            next_since=next_since,
            items=records,
            pagination=pagination,
        )

    def _build_delta(
        self,
        session_id: str,
        since: int,
        records: list[SyncEntityEnvelope],
        has_more: bool,
        next_since: int | None,
        limit: int,
    ) -> DeltaSyncResponseData:
        _ = limit
        created = [rec for rec in records if not rec.deleted_at]
        deleted = [rec for rec in records if rec.deleted_at]
        return DeltaSyncResponseData(
            session_id=session_id,
            since=since,
            has_more=has_more,
            next_since=next_since,
            created=created,
            updated=[],
            deleted=deleted,
        )

    async def apply_changes(
        self, *, session_id: str, user_id: int, client_id: str | None, changes: list[SyncApplyItem]
    ) -> SyncApplyResponseData:
        await self._load_session(session_id, user_id, client_id)
        results: list[SyncApplyItemResult] = []
        for change in changes:
            if change.entity_type != "summary":
                results.append(
                    SyncApplyItemResult(
                        entity_type=change.entity_type,
                        id=change.id,
                        status="invalid",
                        error_code="UNSUPPORTED_ENTITY",
                    )
                )
                continue
            results.append(await self._apply_summary_change(change, user_id))

        conflicts_list = [r for r in results if r.status == "conflict"]
        return SyncApplyResponseData(
            session_id=session_id,
            results=results,
            conflicts=conflicts_list or None,
            has_more=None,
        )

    async def _apply_summary_change(
        self, change: SyncApplyItem, user_id: int
    ) -> SyncApplyItemResult:
        return await SyncApplyService(
            summary_repository=self._summary_repo,
            serializer=self._serializer,
        ).apply_summary_change(change, user_id)
