"""Database synchronization endpoints for offline mobile support."""

import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.api.models.requests import SyncUploadRequest
from app.api.models.responses import (
    SyncChunkData,
    SyncDeltaData,
    SyncSessionInfo,
    SyncUploadResult,
    success_response,
)
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import CrawlResult, Request as RequestModel, Summary
from app.infrastructure.redis import get_redis, redis_key

logger = get_logger(__name__)
router = APIRouter()

# In-memory fallback cache for sync sessions (sync_id -> (expiry_time, chunk_size))
_sync_sessions: dict[str, tuple[datetime, int]] = {}
_cfg: AppConfig | None = None
_redis_warning_logged = False


def _get_cfg() -> AppConfig:
    global _cfg
    if _cfg is None:
        _cfg = load_config(allow_stub_telegram=True)
    return _cfg


def _resolve_chunk_size(requested_chunk_size: int | None, cfg: AppConfig) -> int:
    base = cfg.sync.default_chunk_size
    if requested_chunk_size:
        base = requested_chunk_size
    return max(1, min(500, base))


async def _store_sync_session(
    sync_id: str, chunk_size: int, expires_at: datetime, cfg: AppConfig
) -> None:
    redis_client = await get_redis(cfg)
    ttl_seconds = int(cfg.sync.expiry_hours * 3600)
    if redis_client:
        key = redis_key(cfg.redis.prefix, "sync", "session", sync_id)
        payload = json.dumps({"chunk_size": chunk_size, "expires_at": expires_at.isoformat()})
        await redis_client.set(key, payload, ex=ttl_seconds)
        return

    global _redis_warning_logged
    if not _redis_warning_logged:
        logger.warning("sync_session_redis_unavailable_fallback")
        _redis_warning_logged = True
    _sync_sessions[sync_id] = (expires_at, chunk_size)


async def _validate_sync_session(sync_id: str, cfg: AppConfig) -> int:
    """
    Validate sync session ID and expiry.

    Returns:
        chunk_size for the session

    Raises:
        HTTPException: If sync_id is invalid or expired
    """
    redis_client = await get_redis(cfg)
    if redis_client:
        key = redis_key(cfg.redis.prefix, "sync", "session", sync_id)
        payload = await redis_client.get(key)
        ttl = await redis_client.ttl(key)

        if payload is None or ttl == -2:
            raise HTTPException(
                status_code=404,
                detail="Sync session not found. Please initiate a new sync.",
            )

        if ttl is not None and ttl <= 0:
            await redis_client.delete(key)
            raise HTTPException(
                status_code=410,
                detail="Sync session expired. Please initiate a new sync.",
            )

        try:
            data = json.loads(payload)
            chunk_size = int(data.get("chunk_size", cfg.sync.default_chunk_size))
        except Exception:
            chunk_size = cfg.sync.default_chunk_size

        return max(1, min(500, chunk_size))

    if sync_id not in _sync_sessions:
        raise HTTPException(
            status_code=404,
            detail="Sync session not found. Please initiate a new sync.",
        )

    expiry, chunk_size = _sync_sessions[sync_id]
    if datetime.now(UTC) >= expiry:
        del _sync_sessions[sync_id]
        raise HTTPException(
            status_code=410,
            detail="Sync session expired. Please initiate a new sync.",
        )

    return max(1, min(500, chunk_size))


@router.get("/full")
async def initiate_full_sync(
    since: str | None = Query(None),
    chunk_size: int | None = Query(None, ge=1, le=500),
    user=Depends(get_current_user),
):
    """
    Initiate full database synchronization.

    Returns sync session ID and chunk download URLs.
    """
    cfg = _get_cfg()

    # Build query with user authorization filter
    query = (
        Summary.select()
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])
        .order_by(RequestModel.created_at.desc())
    )

    if since:
        query = query.where(Summary.created_at >= since)

    total_items = query.count()
    resolved_chunk_size = _resolve_chunk_size(chunk_size, cfg)
    chunk_size = resolved_chunk_size
    total_chunks = (total_items + chunk_size - 1) // chunk_size

    # Generate sync session ID
    sync_id = f"sync-{uuid.uuid4().hex[:16]}"

    # Generate chunk URLs
    download_urls = [f"/sync/full/{sync_id}/chunk/{i + 1}" for i in range(total_chunks)]

    # Store sync session with expiry time
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=cfg.sync.expiry_hours)
    await _store_sync_session(sync_id, chunk_size, expires_at, cfg)

    return success_response(
        SyncSessionInfo(
            sync_id=sync_id,
            timestamp=now.isoformat().replace("+00:00", "Z"),
            total_items=total_items,
            chunks=total_chunks,
            download_urls=download_urls,
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        )
    )


@router.get("/full/{sync_id}/chunk/{chunk_number}")
async def download_sync_chunk(
    sync_id: str,
    chunk_number: int,
    user=Depends(get_current_user),
):
    """Download a specific chunk of the database."""
    cfg = _get_cfg()
    # Validate sync session and get chunk size
    chunk_size = await _validate_sync_session(sync_id, cfg)

    # Calculate offset
    offset = (chunk_number - 1) * chunk_size

    # Get summaries for this chunk with eager loading (fixes N+1)
    # Use .select(Summary, RequestModel) to load both in single query
    query = (
        Summary.select(Summary, RequestModel)
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])  # Only user's summaries
        .order_by(RequestModel.created_at.desc())
    )

    summaries = list(query.limit(chunk_size).offset(offset))
    total_chunks = (query.count() + chunk_size - 1) // chunk_size

    # Batch load crawl results for all requests in this chunk (fixes N+1)
    # Single query instead of N queries
    request_ids = [summary.request.id for summary in summaries]
    crawl_results_query = CrawlResult.select().where(CrawlResult.request.in_(request_ids))
    crawl_results_map = {cr.request.id: cr for cr in crawl_results_query}

    items = []
    for summary in summaries:
        # Request is already loaded (no additional query)
        request = summary.request
        json_payload = summary.json_payload or {}

        # Get crawl result from pre-loaded map (no additional query)
        crawl_result = crawl_results_map.get(request.id)
        metadata = crawl_result.metadata_json if crawl_result else {}

        items.append(
            {
                "summary": {
                    "id": summary.id,
                    "request_id": request.id,
                    "json_payload": json_payload,
                    "is_read": summary.is_read,
                    "lang": summary.lang,
                    "created_at": summary.created_at.isoformat() + "Z",
                },
                "request": {
                    "id": request.id,
                    "type": request.type,
                    "status": request.status,
                    "input_url": request.input_url,
                    "normalized_url": request.normalized_url,
                    "created_at": request.created_at.isoformat() + "Z",
                },
                "source": {
                    "title": metadata.get("title"),
                    "domain": metadata.get("domain"),
                    "author": metadata.get("author"),
                    "published_at": metadata.get("published_at"),
                },
            }
        )

    return success_response(
        SyncChunkData(
            sync_id=sync_id,
            chunk_number=chunk_number,
            total_chunks=total_chunks,
            items=items,
        )
    )


@router.get("/delta")
async def get_delta_sync(
    since: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    """Get incremental updates since last sync."""
    # Get created summaries with eager loading (fixes N+1)
    created = (
        Summary.select(Summary, RequestModel)
        .join(RequestModel)
        .where(
            (Summary.created_at > since) & (RequestModel.user_id == user["user_id"])
        )  # Only user's summaries
        .order_by(Summary.created_at.desc())
        .limit(limit)
    )

    created_items = []
    for summary in created:
        # Request is already loaded (no additional query)
        json_payload = summary.json_payload or {}
        created_items.append(
            {
                "summary_id": summary.id,
                "created_at": summary.created_at.isoformat() + "Z",
                "data": {
                    "id": summary.id,
                    "request_id": summary.request.id,
                    "json_payload": json_payload,
                    "is_read": summary.is_read,
                    "lang": summary.lang,
                },
            }
        )

    # Note: Currently only tracks created items. To track updated/deleted items,
    # add updated_at and deleted_at timestamps to Summary model and check against 'since'.
    # This is sufficient for MVP as summaries are immutable after creation.

    return success_response(
        SyncDeltaData(
            changes={"created": created_items, "updated": [], "deleted": []},
            sync_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            has_more=len(created_items) >= limit,
        )
    )


@router.post("/upload-changes")
async def upload_local_changes(
    sync_data: SyncUploadRequest,
    user=Depends(get_current_user),
):
    """Upload local changes from mobile device to server."""
    applied_changes = 0
    conflicts = []

    for change in sync_data.changes:
        # Query with authorization check
        summary = (
            Summary.select()
            .join(RequestModel)
            .where((Summary.id == change.summary_id) & (RequestModel.user_id == user["user_id"]))
            .first()
        )

        if not summary:
            conflicts.append(
                {
                    "summary_id": change.summary_id,
                    "reason": "Summary not found or access denied",
                }
            )
            continue

        if change.action == "update":
            # Apply updates
            for field, value in (change.fields or {}).items():
                if field == "is_read":
                    summary.is_read = value
                # Add more fields as needed

            summary.save()
            applied_changes += 1

        elif change.action == "delete":
            # Soft delete by marking as read (summaries are not permanently deleted)
            # Note: For true soft delete, add 'deleted_at' timestamp field to Summary model
            summary.is_read = True
            summary.save()
            applied_changes += 1

    return success_response(
        SyncUploadResult(
            applied_changes=applied_changes,
            conflicts=conflicts,
            sync_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    )
