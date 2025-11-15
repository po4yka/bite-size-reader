"""
Database synchronization endpoints for offline mobile support.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime, timezone
import uuid

from app.api.auth import get_current_user
from app.api.models.requests import SyncUploadRequest
from app.db.models import Summary, Request as RequestModel, CrawlResult
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/full")
async def initiate_full_sync(
    since: Optional[str] = Query(None),
    chunk_size: int = Query(100, ge=1, le=500),
    user=Depends(get_current_user),
):
    """
    Initiate full database synchronization.

    Returns sync session ID and chunk download URLs.
    """
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
    total_chunks = (total_items + chunk_size - 1) // chunk_size

    # Generate sync session ID
    sync_id = f"sync-{uuid.uuid4().hex[:16]}"

    # Generate chunk URLs
    download_urls = [f"/sync/full/{sync_id}/chunk/{i+1}" for i in range(total_chunks)]

    return {
        "success": True,
        "data": {
            "sync_id": sync_id,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_items": total_items,
            "chunks": total_chunks,
            "download_urls": download_urls,
            "expires_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),  # TODO: Add expiry logic
        },
    }


@router.get("/full/{sync_id}/chunk/{chunk_number}")
async def download_sync_chunk(
    sync_id: str,
    chunk_number: int,
    user=Depends(get_current_user),
):
    """Download a specific chunk of the database."""
    # TODO: Validate sync_id and expiry

    # Calculate offset
    chunk_size = 100
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

    return {
        "success": True,
        "data": {
            "sync_id": sync_id,
            "chunk_number": chunk_number,
            "total_chunks": total_chunks,
            "items": items,
        },
    }


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

    # TODO: Track updated and deleted items
    # For now, just return created items

    return {
        "success": True,
        "data": {
            "changes": {
                "created": created_items,
                "updated": [],
                "deleted": [],
            },
            "sync_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "has_more": len(created_items) >= limit,
        },
    }


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
            .where(
                (Summary.id == change.summary_id) & (RequestModel.user_id == user["user_id"])
            )
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
            # TODO: Implement soft delete
            summary.is_read = True
            summary.save()
            applied_changes += 1

    return {
        "success": True,
        "data": {
            "applied_changes": applied_changes,
            "conflicts": conflicts,
            "sync_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
    }
