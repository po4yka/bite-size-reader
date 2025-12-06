from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from peewee import JOIN

from app.api.models.responses import (
    SyncApplyItemResult,
    SyncApplyResult,
    SyncPage,
    SyncRecord,
    SyncSessionInfo,
)
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request, Summary, User
from app.infrastructure.redis import get_redis, redis_key

if TYPE_CHECKING:
    from app.api.models.requests import SyncApplyItem
    from app.config import AppConfig

logger = get_logger(__name__)

_sync_sessions: dict[str, dict[str, Any]] = {}
_redis_warning_logged = False


class SyncService:
    """Sync protocol service implementing sessions, delta/full retrieval, and apply."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg

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
            await redis_client.set(key, json.dumps(payload), ex=ttl_seconds)
            return

        global _redis_warning_logged
        if not _redis_warning_logged:
            logger.warning("sync_session_redis_unavailable_fallback")
            _redis_warning_logged = True
        _sync_sessions[payload["session_id"]] = payload

    async def _load_session(
        self, session_id: str, user_id: int, client_id: str | None
    ) -> dict[str, Any]:
        redis_client = await get_redis(self.cfg)
        if redis_client:
            key = redis_key(self.cfg.redis.prefix, "sync", "session", session_id)
            payload_raw = await redis_client.get(key)
            ttl = await redis_client.ttl(key)

            if payload_raw is None or ttl == -2:
                raise HTTPException(status_code=410, detail="Sync session expired or not found")

            payload = json.loads(payload_raw)
        else:
            payload = _sync_sessions.get(session_id)
            if not payload:
                raise HTTPException(status_code=410, detail="Sync session expired or not found")

        if payload.get("user_id") != user_id or payload.get("client_id") != client_id:
            raise HTTPException(
                status_code=403, detail="Sync session does not belong to this user/client"
            )

        expires_raw = payload["expires_at"]
        expires_at = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if datetime.now(UTC) >= expires_at:
            raise HTTPException(status_code=410, detail="Sync session expired")

        return payload

    async def start_session(
        self, *, user_id: int, client_id: str | None, limit: int | None
    ) -> SyncSessionInfo:
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

        return SyncSessionInfo(
            session_id=session_id,
            expires_at=payload["expires_at"],
            chunk_limit=resolved,
            created_at=payload["created_at"],
        )

    def _serialize_request(self, request: Request) -> SyncRecord:
        deleted_at = request.deleted_at.isoformat() + "Z" if request.deleted_at else None
        data = (
            None
            if request.is_deleted
            else {
                "type": request.type,
                "status": request.status,
                "input_url": request.input_url,
                "normalized_url": request.normalized_url,
                "correlation_id": request.correlation_id,
                "created_at": request.created_at.isoformat() + "Z",
            }
        )
        return SyncRecord(
            entity_type="request",
            id=request.id,
            server_version=int(request.server_version or 0),
            updated_at=request.updated_at.isoformat() + "Z",
            deleted_at=deleted_at,
            data=data,
        )

    def _serialize_summary(self, summary: Summary) -> SyncRecord:
        deleted_at = summary.deleted_at.isoformat() + "Z" if summary.deleted_at else None
        payload = None
        if not summary.is_deleted:
            payload = {
                "id": summary.id,
                "request_id": summary.request.id,
                "lang": summary.lang,
                "is_read": summary.is_read,
                "json_payload": summary.json_payload,
                "created_at": summary.created_at.isoformat() + "Z",
            }

        return SyncRecord(
            entity_type="summary",
            id=summary.id,
            server_version=int(summary.server_version or 0),
            updated_at=summary.updated_at.isoformat() + "Z",
            deleted_at=deleted_at,
            data=payload,
        )

    def _serialize_crawl_result(self, crawl: CrawlResult) -> SyncRecord:
        deleted_at = crawl.deleted_at.isoformat() + "Z" if crawl.deleted_at else None
        payload = None
        if not crawl.is_deleted:
            payload = {
                "request_id": crawl.request.id,
                "source_url": crawl.source_url,
                "endpoint": crawl.endpoint,
                "http_status": crawl.http_status,
                "metadata": crawl.metadata_json,
                "latency_ms": crawl.latency_ms,
            }

        return SyncRecord(
            entity_type="crawl_result",
            id=crawl.id,
            server_version=int(crawl.server_version or 0),
            updated_at=crawl.updated_at.isoformat() + "Z",
            deleted_at=deleted_at,
            data=payload,
        )

    def _serialize_llm_call(self, call: LLMCall) -> SyncRecord:
        deleted_at = call.deleted_at.isoformat() + "Z" if call.deleted_at else None
        payload = None
        if not call.is_deleted:
            payload = {
                "request_id": call.request.id,
                "provider": call.provider,
                "model": call.model,
                "status": call.status,
                "tokens_prompt": call.tokens_prompt,
                "tokens_completion": call.tokens_completion,
                "cost_usd": call.cost_usd,
                "created_at": call.created_at.isoformat() + "Z",
            }

        return SyncRecord(
            entity_type="llm_call",
            id=call.id,
            server_version=int(call.server_version or 0),
            updated_at=call.updated_at.isoformat() + "Z",
            deleted_at=deleted_at,
            data=payload,
        )

    def _serialize_user(self, user: User) -> SyncRecord:
        return SyncRecord(
            entity_type="user",
            id=user.telegram_user_id,
            server_version=int(user.server_version or 0),
            updated_at=user.updated_at.isoformat() + "Z",
            data={
                "username": user.username,
                "is_owner": user.is_owner,
                "preferences": user.preferences_json,
                "created_at": user.created_at.isoformat() + "Z",
            },
        )

    def _collect_records(self, user_id: int) -> list[SyncRecord]:
        records: list[SyncRecord] = []

        user = User.select().where(User.telegram_user_id == user_id).first()
        if user:
            records.append(self._serialize_user(user))

        for request in Request.select().where(Request.user_id == user_id):
            records.append(self._serialize_request(request))

        for summary in (
            Summary.select(Summary, Request).join(Request).where(Request.user_id == user_id)
        ):
            records.append(self._serialize_summary(summary))

        for crawl in (
            CrawlResult.select(CrawlResult, Request)
            .join(Request, JOIN.INNER)
            .where(Request.user_id == user_id)
        ):
            records.append(self._serialize_crawl_result(crawl))

        for call in (
            LLMCall.select(LLMCall, Request)
            .join(Request, JOIN.INNER)
            .where(Request.user_id == user_id)
        ):
            records.append(self._serialize_llm_call(call))

        records.sort(key=lambda r: (r.server_version, str(r.id)))
        return records

    def _paginate_records(
        self, records: Iterable[SyncRecord], since: int, limit: int
    ) -> tuple[list[SyncRecord], bool, int | None]:
        filtered = [rec for rec in records if rec.server_version > since]
        page = filtered[:limit]
        has_more = len(filtered) > limit
        next_since = page[-1].server_version if page else since
        return page, has_more, next_since

    async def get_full(
        self, *, session_id: str, user_id: int, client_id: str | None, limit: int | None
    ) -> SyncPage:
        session = await self._load_session(session_id, user_id, client_id)
        resolved_limit = self._resolve_limit(limit or session.get("chunk_limit"))
        records = self._collect_records(user_id)
        page, has_more, next_since = self._paginate_records(records, since=0, limit=resolved_limit)
        return self._build_page(session_id, page, has_more, next_since, resolved_limit)

    async def get_delta(
        self, *, session_id: str, user_id: int, client_id: str | None, since: int, limit: int | None
    ) -> SyncPage:
        session = await self._load_session(session_id, user_id, client_id)
        resolved_limit = self._resolve_limit(limit or session.get("chunk_limit"))
        records = self._collect_records(user_id)
        page, has_more, next_since = self._paginate_records(
            records, since=since, limit=resolved_limit
        )
        return self._build_page(session_id, page, has_more, next_since, resolved_limit)

    def _build_page(
        self,
        session_id: str,
        records: list[SyncRecord],
        has_more: bool,
        next_since: int | None,
        limit: int,
    ) -> SyncPage:
        created = [rec for rec in records if not rec.deleted_at]
        updated: list[SyncRecord] = []
        deleted = [rec for rec in records if rec.deleted_at]

        return SyncPage(
            session_id=session_id,
            created=created,
            updated=updated,
            deleted=deleted,
            has_more=has_more,
            next_since=next_since,
            limit=limit,
        )

    async def apply_changes(
        self, *, session_id: str, user_id: int, client_id: str | None, changes: list[SyncApplyItem]
    ) -> SyncApplyResult:
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

            result = self._apply_summary_change(change, user_id)
            results.append(result)
            if result.status == "applied":
                applied += 1
            elif result.status == "conflict":
                conflicts += 1
            else:
                invalid += 1

        return SyncApplyResult(
            session_id=session_id,
            results=results,
            applied=applied,
            conflicts=conflicts,
            invalid=invalid,
            sync_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )

    def _apply_summary_change(self, change: SyncApplyItem, user_id: int) -> SyncApplyItemResult:
        summary = (
            Summary.select(Summary, Request)
            .join(Request)
            .where((Summary.id == change.id) & (Request.user_id == user_id))
            .first()
        )

        if not summary:
            return SyncApplyItemResult(
                entity_type=change.entity_type,
                id=change.id,
                status="invalid",
                error_code="NOT_FOUND",
            )

        current_version = int(summary.server_version or 0)
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

        if change.action == "delete":
            summary.is_deleted = True
            summary.deleted_at = datetime.now(UTC)
        elif "is_read" in payload:
            summary.is_read = bool(payload["is_read"])

        summary.save()

        return SyncApplyItemResult(
            entity_type=change.entity_type,
            id=change.id,
            status="applied",
            server_version=int(summary.server_version or 0),
        )
