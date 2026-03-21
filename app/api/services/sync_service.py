"""Sync service - device sync business logic.

TODO: Migrate to app/application/services/ following the pattern established
by request_service.py. This file remains in app/api/services/ for backward
compatibility until the migration is complete.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.api.exceptions import (
    SyncSessionExpiredError,
    SyncSessionForbiddenError,
    SyncSessionNotFoundError,
)
from app.api.models.responses import (
    DeltaSyncResponseData,
    FullSyncResponseData,
    PaginationInfo,
    SyncApplyItemResult,
    SyncApplyResponseData,
    SyncEntityEnvelope,
    SyncSessionData,
)
from app.core.json_utils import dumps as json_dumps, loads as json_loads
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.di.repositories import (
    build_crawl_result_repository,
    build_llm_repository,
    build_request_repository,
    build_summary_repository,
    build_user_repository,
)
from app.infrastructure.redis import get_redis, redis_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.api.models.requests import SyncApplyItem
    from app.application.ports import (
        CrawlResultRepositoryPort,
        LLMRepositoryPort,
        RequestRepositoryPort,
        SummaryRepositoryPort,
        UserRepositoryPort,
    )
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
        SqliteCrawlResultRepositoryAdapter,
    )
    from app.infrastructure.persistence.sqlite.repositories.llm_repository import (
        SqliteLLMRepositoryAdapter,
    )
    from app.infrastructure.persistence.sqlite.repositories.request_repository import (
        SqliteRequestRepositoryAdapter,
    )
    from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
        SqliteSummaryRepositoryAdapter,
    )
    from app.infrastructure.persistence.sqlite.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )
else:

    class SqliteCrawlResultRepositoryAdapter:
        pass

    class SqliteLLMRepositoryAdapter:
        pass

    class SqliteRequestRepositoryAdapter:
        pass

    class SqliteSummaryRepositoryAdapter:
        pass

    class SqliteUserRepositoryAdapter:
        pass


logger = get_logger(__name__)


def _parse_session_expires_at(payload: dict[str, Any]) -> datetime | None:
    """Parse a fallback session expiry timestamp."""
    expires_raw = payload.get("expires_at")
    if not isinstance(expires_raw, str) or not expires_raw:
        return None
    try:
        return datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class SyncService:
    """Sync protocol service implementing sessions, delta/full retrieval, and apply."""

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
    ) -> None:
        self.cfg = cfg
        self._session_manager = session_manager
        self._sync_sessions: dict[str, dict[str, Any]] = {}
        self._redis_warning_logged = False

        self._user_repo = user_repository or build_user_repository(session_manager)
        self._request_repo = request_repository or build_request_repository(session_manager)
        self._summary_repo = summary_repository or build_summary_repository(session_manager)
        self._crawl_repo = crawl_result_repository or build_crawl_result_repository(session_manager)
        self._llm_repo = llm_repository or build_llm_repository(session_manager)

    async def get_max_server_version(self, user_id: int) -> int:
        """Get the maximum server_version across all synced entity tables."""
        import asyncio

        versions = await asyncio.gather(
            self._user_repo.async_get_max_server_version(user_id),
            self._request_repo.async_get_max_server_version(user_id),
            self._summary_repo.async_get_max_server_version(user_id),
            self._crawl_repo.async_get_max_server_version(user_id),
            self._llm_repo.async_get_max_server_version(user_id),
        )
        return max((v for v in versions if v is not None), default=0)

    def _prune_fallback_sessions(
        self, now: datetime, *, exclude_session_id: str | None = None
    ) -> int:
        """Remove expired in-memory sync sessions."""
        expired_session_ids = []
        for session_id, payload in self._sync_sessions.items():
            if exclude_session_id is not None and session_id == exclude_session_id:
                continue
            expires_at = _parse_session_expires_at(payload)
            if expires_at is not None and now >= expires_at:
                expired_session_ids.append(session_id)

        for session_id in expired_session_ids:
            self._sync_sessions.pop(session_id, None)
        return len(expired_session_ids)

    def _resolve_limit(self, requested: int | None) -> int:
        return max(
            self.cfg.sync.min_limit,
            min(self.cfg.sync.max_limit, requested or self.cfg.sync.default_limit),
        )

    async def _store_session(self, payload: dict[str, Any]) -> None:
        redis_client = await get_redis(self.cfg)
        ttl_seconds = int(self.cfg.sync.expiry_hours * 3600)

        if redis_client:
            key = redis_key(self.cfg.redis.prefix, "sync", "session", payload["session_id"])
            await redis_client.set(key, json_dumps(payload), ex=ttl_seconds)
            return

        if not self._redis_warning_logged:
            logger.warning("sync_session_redis_unavailable_fallback")
            self._redis_warning_logged = True
        self._prune_fallback_sessions(datetime.now(UTC))
        self._sync_sessions[payload["session_id"]] = payload

    async def _load_session(
        self, session_id: str, user_id: int, client_id: str | None
    ) -> dict[str, Any]:
        redis_client = await get_redis(self.cfg)
        if redis_client:
            key = redis_key(self.cfg.redis.prefix, "sync", "session", session_id)
            payload_raw = await redis_client.get(key)
            ttl = await redis_client.ttl(key)

            if payload_raw is None or ttl == -2:
                raise SyncSessionNotFoundError(session_id)

            payload = json_loads(payload_raw)
        else:
            self._prune_fallback_sessions(datetime.now(UTC), exclude_session_id=session_id)
            payload = self._sync_sessions.get(session_id)
            if not payload:
                raise SyncSessionNotFoundError(session_id)

        if payload.get("user_id") != user_id or payload.get("client_id") != client_id:
            raise SyncSessionForbiddenError()

        expires_raw = payload["expires_at"]
        expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if datetime.now(UTC) >= expires_at:
            if redis_client is None:
                self._sync_sessions.pop(session_id, None)
            raise SyncSessionExpiredError(session_id)

        return payload

    async def start_session(
        self, *, user_id: int, client_id: str | None, limit: int | None
    ) -> SyncSessionData:
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

    def _deleted_at(self, record: dict[str, Any]) -> str | None:
        """Return ISO-8601 deleted_at string, or None if not set."""
        raw = record.get("deleted_at")
        return self._coerce_iso(raw) if raw else None

    @staticmethod
    def _resolve_request_id(record: dict[str, Any]) -> int | None:
        """Extract request_id from a record where 'request' may be int or dict."""
        request_val = record.get("request")
        if isinstance(request_val, int):
            return request_val
        if isinstance(request_val, dict):
            return request_val.get("id")
        return None

    def _serialize_request(self, request: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a request dict to SyncEntityEnvelope."""
        payload = None
        if not request.get("is_deleted"):
            payload = {
                "id": request.get("id"),
                "type": request.get("type"),
                "status": request.get("status"),
                "input_url": request.get("input_url"),
                "normalized_url": request.get("normalized_url"),
                "correlation_id": request.get("correlation_id"),
                "created_at": self._coerce_iso(request.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="request",
            id=request.get("id"),
            server_version=int(request.get("server_version") or 0),
            updated_at=self._coerce_iso(request.get("updated_at")),
            deleted_at=self._deleted_at(request),
            request=payload,
        )

    def _serialize_summary(self, summary: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a summary dict to SyncEntityEnvelope."""
        payload = None
        if not summary.get("is_deleted"):
            payload = {
                "id": summary.get("id"),
                "request_id": self._resolve_request_id(summary),
                "lang": summary.get("lang"),
                "is_read": summary.get("is_read"),
                "json_payload": summary.get("json_payload"),
                "created_at": self._coerce_iso(summary.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="summary",
            id=summary.get("id"),
            server_version=int(summary.get("server_version") or 0),
            updated_at=self._coerce_iso(summary.get("updated_at")),
            deleted_at=self._deleted_at(summary),
            summary=payload,
        )

    def _serialize_crawl_result(self, crawl: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a crawl result dict to SyncEntityEnvelope."""
        payload = None
        if not crawl.get("is_deleted"):
            payload = {
                "request_id": self._resolve_request_id(crawl),
                "source_url": crawl.get("source_url"),
                "endpoint": crawl.get("endpoint"),
                "http_status": crawl.get("http_status"),
                "metadata": crawl.get("metadata_json"),
                "latency_ms": crawl.get("latency_ms"),
            }
        return SyncEntityEnvelope(
            entity_type="crawl_result",
            id=crawl.get("id"),
            server_version=int(crawl.get("server_version") or 0),
            updated_at=self._coerce_iso(crawl.get("updated_at")),
            deleted_at=self._deleted_at(crawl),
            crawl_result=payload,
        )

    def _serialize_llm_call(self, call: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize an LLM call dict to SyncEntityEnvelope."""
        payload = None
        if not call.get("is_deleted"):
            payload = {
                "request_id": self._resolve_request_id(call),
                "provider": call.get("provider"),
                "model": call.get("model"),
                "status": call.get("status"),
                "tokens_prompt": call.get("tokens_prompt"),
                "tokens_completion": call.get("tokens_completion"),
                "cost_usd": call.get("cost_usd"),
                "created_at": self._coerce_iso(call.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="llm_call",
            id=call.get("id"),
            server_version=int(call.get("server_version") or 0),
            updated_at=self._coerce_iso(call.get("updated_at")),
            deleted_at=self._deleted_at(call),
            llm_call=payload,
        )

    def _coerce_iso(self, dt_value: Any) -> str:
        """Safely convert datetime-ish values (including strings) to ISO 8601 Z form."""
        if hasattr(dt_value, "isoformat") and not isinstance(dt_value, str):
            return dt_value.isoformat() + "Z"
        if isinstance(dt_value, str):
            try:
                return datetime.fromisoformat(dt_value.replace("Z", "+00:00")).isoformat() + "Z"
            except Exception:
                logger.warning("datetime_parse_failed", exc_info=True)
                return datetime.now(UTC).isoformat() + "Z"
        return datetime.now(UTC).isoformat() + "Z"

    def _serialize_highlight(self, highlight: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a highlight dict to SyncEntityEnvelope."""
        # Handle summary as either dict or int/UUID
        summary_val = highlight.get("summary")
        summary_id = summary_val.get("id") if isinstance(summary_val, dict) else summary_val

        payload = {
            "id": str(highlight.get("id")),
            "summary_id": str(summary_id) if summary_id is not None else None,
            "text": highlight.get("text"),
            "start_offset": highlight.get("start_offset"),
            "end_offset": highlight.get("end_offset"),
            "color": highlight.get("color"),
            "note": highlight.get("note"),
            "created_at": self._coerce_iso(highlight.get("created_at")),
            "updated_at": self._coerce_iso(highlight.get("updated_at")),
        }

        return SyncEntityEnvelope(
            entity_type="highlight",
            id=str(highlight.get("id")),
            server_version=int(highlight.get("server_version") or 0),
            updated_at=self._coerce_iso(highlight.get("updated_at")),
            highlight=payload,
        )

    def _serialize_user(self, user: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a user dict to SyncEntityEnvelope."""
        updated_at = user.get("updated_at")
        created_at = user.get("created_at")
        return SyncEntityEnvelope(
            entity_type="user",
            id=user.get("telegram_user_id"),
            server_version=int(user.get("server_version") or 0),
            updated_at=self._coerce_iso(updated_at),
            preference={
                "username": user.get("username"),
                "is_owner": user.get("is_owner"),
                "preferences": user.get("preferences_json"),
                "created_at": self._coerce_iso(created_at),
            },
        )

    def _serialize_tag(self, tag: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a tag dict to SyncEntityEnvelope."""
        payload = None
        if not tag.get("is_deleted"):
            payload = {
                "id": tag.get("id"),
                "name": tag.get("name"),
                "normalized_name": tag.get("normalized_name"),
                "color": tag.get("color"),
                "server_version": int(tag.get("server_version") or 0),
                "is_deleted": tag.get("is_deleted", False),
                "created_at": self._coerce_iso(tag.get("created_at")),
                "updated_at": self._coerce_iso(tag.get("updated_at")),
            }
        return SyncEntityEnvelope(
            entity_type="tag",
            id=tag.get("id"),
            server_version=int(tag.get("server_version") or 0),
            updated_at=self._coerce_iso(tag.get("updated_at")),
            deleted_at=self._deleted_at(tag),
            tag=payload,
        )

    def _serialize_summary_tag(self, st: dict[str, Any]) -> SyncEntityEnvelope:
        """Serialize a summary_tag dict to SyncEntityEnvelope."""
        summary_val = st.get("summary")
        summary_id = summary_val.get("id") if isinstance(summary_val, dict) else summary_val
        tag_val = st.get("tag")
        tag_id = tag_val.get("id") if isinstance(tag_val, dict) else tag_val

        payload = {
            "id": st.get("id"),
            "summary_id": summary_id,
            "tag_id": tag_id,
            "source": st.get("source"),
            "server_version": int(st.get("server_version") or 0),
            "created_at": self._coerce_iso(st.get("created_at")),
        }
        return SyncEntityEnvelope(
            entity_type="summary_tag",
            id=st.get("id"),
            server_version=int(st.get("server_version") or 0),
            updated_at=self._coerce_iso(st.get("created_at")),
            summary_tag=payload,
        )

    @staticmethod
    def _get_highlights_for_user(user_id: int) -> list[dict[str, Any]]:
        """Fetch all highlights for a user as dicts."""
        from app.db.models import SummaryHighlight, model_to_dict

        rows = SummaryHighlight.select().where(SummaryHighlight.user == user_id)
        return [d for row in rows if (d := model_to_dict(row)) is not None]

    @staticmethod
    def _get_tags_for_user(user_id: int) -> list[dict[str, Any]]:
        """Fetch all tags for a user as dicts (including soft-deleted)."""
        from app.db.models import Tag, model_to_dict

        rows = Tag.select().where(Tag.user == user_id)
        return [d for row in rows if (d := model_to_dict(row)) is not None]

    @staticmethod
    def _get_summary_tags_for_user(user_id: int) -> list[dict[str, Any]]:
        """Fetch all summary_tags for a user's summaries as dicts."""
        from app.db.models import Request, Summary, SummaryTag, model_to_dict

        rows = (
            SummaryTag.select()
            .join(Summary, on=(SummaryTag.summary == Summary.id))
            .join(Request, on=(Summary.request == Request.id))
            .where(Request.user_id == user_id)
        )
        return [d for row in rows if (d := model_to_dict(row)) is not None]

    async def _collect_records(self, user_id: int) -> list[SyncEntityEnvelope]:
        """Collect all sync records for a user using repository adapters."""
        records: list[SyncEntityEnvelope] = []

        # Get user data
        user = await self._user_repo.async_get_user_by_telegram_id(user_id)
        if user:
            records.append(self._serialize_user(user))

        # Get all requests for user
        requests = await self._request_repo.async_get_all_for_user(user_id)
        for request in requests:
            records.append(self._serialize_request(request))

        # Get all summaries for user
        summaries = await self._summary_repo.async_get_all_for_user(user_id)
        for summary in summaries:
            records.append(self._serialize_summary(summary))

        # Get all crawl results for user
        crawl_results = await self._crawl_repo.async_get_all_for_user(user_id)
        for crawl in crawl_results:
            records.append(self._serialize_crawl_result(crawl))

        # Get all LLM calls for user
        llm_calls = await self._llm_repo.async_get_all_for_user(user_id)
        for call in llm_calls:
            records.append(self._serialize_llm_call(call))

        # Get all highlights for user
        highlights = self._get_highlights_for_user(user_id)
        for highlight in highlights:
            records.append(self._serialize_highlight(highlight))

        # Get all tags for user
        tags = self._get_tags_for_user(user_id)
        for tag in tags:
            records.append(self._serialize_tag(tag))

        # Get all summary_tags for user
        summary_tags = self._get_summary_tags_for_user(user_id)
        for st in summary_tags:
            records.append(self._serialize_summary_tag(st))

        # Sort by server_version and id for consistent ordering
        records.sort(key=lambda r: (r.server_version, str(r.id)))
        return records

    def _paginate_records(
        self, records: Iterable[SyncEntityEnvelope], since: int, limit: int
    ) -> tuple[list[SyncEntityEnvelope], bool, int | None]:
        filtered = [rec for rec in records if rec.server_version > since]
        page = filtered[:limit]
        has_more = len(filtered) > limit
        next_since = page[-1].server_version if page else since
        return page, has_more, next_since

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
        created = [rec for rec in records if not rec.deleted_at]
        updated: list[SyncEntityEnvelope] = []
        deleted = [rec for rec in records if rec.deleted_at]

        return DeltaSyncResponseData(
            session_id=session_id,
            since=since,
            has_more=has_more,
            next_since=next_since,
            created=created,
            updated=updated,
            deleted=deleted,
        )

    async def apply_changes(
        self, *, session_id: str, user_id: int, client_id: str | None, changes: list[SyncApplyItem]
    ) -> SyncApplyResponseData:
        await self._load_session(session_id, user_id, client_id)

        results: list[SyncApplyItemResult] = []
        applied = conflicts = invalid = 0

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
                invalid += 1
                continue

            result = await self._apply_summary_change(change, user_id)
            results.append(result)
            if result.status == "applied":
                applied += 1
            elif result.status == "conflict":
                conflicts += 1
            else:
                invalid += 1

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
        """Apply a change to a summary using repository methods."""
        try:
            summary_id = int(change.id)
        except (ValueError, TypeError):
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="INVALID_ID",
            )

        summary = await self._summary_repo.async_get_summary_for_sync_apply(summary_id, user_id)

        if not summary:
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="NOT_FOUND",
            )

        current_version = int(summary.get("server_version") or 0)
        if change.last_seen_version < current_version:
            snapshot = self._serialize_summary(summary).model_dump()
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="conflict",
                server_version=current_version,
                server_snapshot=snapshot,
                error_code="CONFLICT_VERSION",
            )

        payload = change.payload or {}
        allowed_fields = {"is_read"}
        invalid_fields = [field for field in payload if field not in allowed_fields]
        if invalid_fields:
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="INVALID_FIELDS",
                server_version=current_version,
            )

        # Apply the change using repository
        is_deleted = None
        deleted_at = None
        is_read = None

        if change.action == "delete":
            is_deleted = True
            deleted_at = datetime.now(UTC)
        elif "is_read" in payload:
            is_read = bool(payload["is_read"])

        new_version = await self._summary_repo.async_apply_sync_change(
            summary_id,
            is_deleted=is_deleted,
            deleted_at=deleted_at,
            is_read=is_read,
        )

        return SyncApplyItemResult(
            entity_type=change.entity_type,
            id=change.id,
            status="applied",
            server_version=new_version,
        )
