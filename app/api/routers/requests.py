"""
Request submission and status endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Union
from datetime import datetime

from app.api.auth import get_current_user
from app.api.models.requests import SubmitURLRequest, SubmitForwardRequest
from app.db.models import Request as RequestModel, Summary, CrawlResult, LLMCall
from app.core.url_utils import normalize_url, compute_dedupe_hash
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("")
async def submit_request(
    request_data: Union[SubmitURLRequest, SubmitForwardRequest],
    user=Depends(get_current_user),
):
    """
    Submit a new URL or forwarded message for processing.

    Returns request_id and correlation_id for status polling.
    Checks for duplicates and returns existing summary if found.
    """
    # Handle URL request
    if isinstance(request_data, SubmitURLRequest):
        input_url = str(request_data.input_url)
        normalized = normalize_url(input_url)
        dedupe_hash = compute_dedupe_hash(normalized)

        # Check for duplicate
        existing = RequestModel.select().where(RequestModel.dedupe_hash == dedupe_hash).first()

        if existing:
            summary = Summary.select().where(Summary.request == existing).first()

            return {
                "success": True,
                "data": {
                    "is_duplicate": True,
                    "existing_request_id": existing.id,
                    "existing_summary_id": summary.id if summary else None,
                    "message": "This URL was already summarized",
                    "summarized_at": existing.created_at.isoformat() + "Z",
                },
            }

        # Create new request
        correlation_id = f"api-{user['user_id']}-{int(datetime.utcnow().timestamp())}"

        new_request = RequestModel.create(
            type="url",
            status="pending",
            correlation_id=correlation_id,
            user_id=user["user_id"],
            input_url=input_url,
            normalized_url=normalized,
            dedupe_hash=dedupe_hash,
            lang_detected=request_data.lang_preference,
        )

        # TODO: Trigger async processing (Celery task or background job)
        # For now, just return the request
        logger.info(
            f"New URL request created: {new_request.id}",
            extra={"correlation_id": correlation_id},
        )

        return {
            "success": True,
            "data": {
                "request_id": new_request.id,
                "correlation_id": correlation_id,
                "type": "url",
                "status": "pending",
                "estimated_wait_seconds": 15,
                "created_at": new_request.created_at.isoformat() + "Z",
                "is_duplicate": False,
            },
        }

    # Handle forward request
    else:
        correlation_id = f"api-{user['user_id']}-{int(datetime.utcnow().timestamp())}"

        new_request = RequestModel.create(
            type="forward",
            status="pending",
            correlation_id=correlation_id,
            user_id=user["user_id"],
            content_text=request_data.content_text,
            fwd_from_chat_id=request_data.forward_metadata.from_chat_id,
            fwd_from_msg_id=request_data.forward_metadata.from_message_id,
            lang_detected=request_data.lang_preference,
        )

        # TODO: Trigger async processing
        logger.info(
            f"New forward request created: {new_request.id}",
            extra={"correlation_id": correlation_id},
        )

        return {
            "success": True,
            "data": {
                "request_id": new_request.id,
                "correlation_id": correlation_id,
                "type": "forward",
                "status": "pending",
                "estimated_wait_seconds": 10,
                "created_at": new_request.created_at.isoformat() + "Z",
                "is_duplicate": False,
            },
        }


@router.get("/{request_id}")
async def get_request(
    request_id: int,
    user=Depends(get_current_user),
):
    """Get details about a specific request."""
    request = RequestModel.select().where(RequestModel.id == request_id).first()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Get related records
    crawl_result = CrawlResult.select().where(CrawlResult.request == request).first()
    llm_calls = list(LLMCall.select().where(LLMCall.request == request))
    summary = Summary.select().where(Summary.request == request).first()

    return {
        "success": True,
        "data": {
            "request": {
                "id": request.id,
                "type": request.type,
                "status": request.status,
                "correlation_id": request.correlation_id,
                "input_url": request.input_url,
                "normalized_url": request.normalized_url,
                "dedupe_hash": request.dedupe_hash,
                "created_at": request.created_at.isoformat() + "Z",
                "lang_detected": request.lang_detected,
            },
            "crawl_result": {
                "status": crawl_result.status if crawl_result else None,
                "http_status": crawl_result.http_status if crawl_result else None,
                "latency_ms": crawl_result.latency_ms if crawl_result else None,
                "error": crawl_result.error_text if crawl_result else None,
            }
            if crawl_result
            else None,
            "llm_calls": [
                {
                    "id": call.id,
                    "model": call.model,
                    "status": call.status,
                    "tokens_prompt": call.tokens_prompt,
                    "tokens_completion": call.tokens_completion,
                    "cost_usd": call.cost_usd,
                    "latency_ms": call.latency_ms,
                    "created_at": call.created_at.isoformat() + "Z",
                }
                for call in llm_calls
            ],
            "summary": {
                "id": summary.id,
                "status": "success",
                "created_at": summary.created_at.isoformat() + "Z",
            }
            if summary
            else None,
        },
    }


@router.get("/{request_id}/status")
async def get_request_status(
    request_id: int,
    user=Depends(get_current_user),
):
    """Poll for real-time processing status."""
    request = RequestModel.select().where(RequestModel.id == request_id).first()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Determine stage based on status and related records
    stage = None
    progress = None

    if request.status == "processing":
        # Check which stage we're in
        crawl_result = CrawlResult.select().where(CrawlResult.request == request).first()
        llm_calls = LLMCall.select().where(LLMCall.request == request).count()
        summary = Summary.select().where(Summary.request == request).first()

        if not crawl_result:
            stage = "content_extraction"
            progress = {"current_step": 1, "total_steps": 4, "percentage": 25}
        elif llm_calls == 0:
            stage = "llm_summarization"
            progress = {"current_step": 2, "total_steps": 4, "percentage": 50}
        elif not summary:
            stage = "validation"
            progress = {"current_step": 3, "total_steps": 4, "percentage": 75}

    return {
        "success": True,
        "data": {
            "request_id": request.id,
            "status": request.status,
            "stage": stage,
            "progress": progress,
            "estimated_seconds_remaining": 8 if request.status == "processing" else None,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        },
    }


@router.post("/{request_id}/retry")
async def retry_request(
    request_id: int,
    user=Depends(get_current_user),
):
    """Retry a failed request."""
    original_request = RequestModel.select().where(RequestModel.id == request_id).first()

    if not original_request:
        raise HTTPException(status_code=404, detail="Request not found")

    if original_request.status != "error":
        raise HTTPException(status_code=400, detail="Only failed requests can be retried")

    # Create new request with retry correlation ID
    correlation_id = f"{original_request.correlation_id}-retry-1"

    new_request = RequestModel.create(
        type=original_request.type,
        status="pending",
        correlation_id=correlation_id,
        user_id=user["user_id"],
        input_url=original_request.input_url,
        normalized_url=original_request.normalized_url,
        dedupe_hash=original_request.dedupe_hash,
        content_text=original_request.content_text,
        fwd_from_chat_id=original_request.fwd_from_chat_id,
        fwd_from_msg_id=original_request.fwd_from_msg_id,
        lang_detected=original_request.lang_detected,
    )

    # TODO: Trigger async processing
    logger.info(
        f"Retry request created: {new_request.id} (original: {request_id})",
        extra={"correlation_id": correlation_id},
    )

    return {
        "success": True,
        "data": {
            "new_request_id": new_request.id,
            "correlation_id": correlation_id,
            "status": "pending",
            "created_at": new_request.created_at.isoformat() + "Z",
        },
    }
