"""
Request submission and status endpoints.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from peewee import OperationalError

from app.api.auth import get_current_user
from app.api.background_processor import process_url_request
from app.api.exceptions import DuplicateResourceError
from app.api.models.requests import SubmitForwardRequest, SubmitURLRequest
from app.api.models.responses import (
    RequestStatus,
    RequestStatusData,
    SubmitRequestData,
    SubmitRequestResponse,
    success_response,
)
from app.api.services import RequestService
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import Request as RequestModel

logger = get_logger(__name__)
router = APIRouter()


@router.post("")
async def submit_request(
    request_data: SubmitURLRequest | SubmitForwardRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """
    Submit a new URL or forwarded message for processing.

    Returns request_id and correlation_id for status polling.
    Checks for duplicates and returns existing summary if found.
    Processing happens asynchronously in the background.
    """
    # Handle URL request
    if isinstance(request_data, SubmitURLRequest):
        input_url = str(request_data.input_url)

        # Check for duplicate using service
        duplicate_info = RequestService.check_duplicate_url(user["user_id"], input_url)
        if duplicate_info:
            return success_response(
                {
                    "is_duplicate": True,
                    "existing_request_id": duplicate_info["existing_request_id"],
                    "existing_summary_id": duplicate_info["existing_summary_id"],
                    "message": "This URL was already summarized",
                    "summarized_at": duplicate_info["summarized_at"],
                }
            )

        # Create new request using service
        try:
            new_request = RequestService.create_url_request(
                user_id=user["user_id"],
                input_url=input_url,
                lang_preference=request_data.lang_preference,
            )
        except DuplicateResourceError as e:
            # Race condition - handle gracefully
            return success_response(
                {
                    "is_duplicate": True,
                    "existing_request_id": e.details.get("existing_id"),
                    "message": e.message,
                }
            )

        # Schedule background processing
        background_tasks.add_task(process_url_request, new_request.id)

        payload = SubmitRequestResponse(
            request_id=new_request.id,
            correlation_id=new_request.correlation_id,
            type="url",
            status="pending",
            estimated_wait_seconds=15,
            created_at=new_request.created_at.isoformat() + "Z",
            is_duplicate=False,
        )
        return success_response(SubmitRequestData(request=payload))

    # Handle forward request
    # Create new forward request using service
    new_request = RequestService.create_forward_request(
        user_id=user["user_id"],
        content_text=request_data.content_text,
        from_chat_id=request_data.forward_metadata.from_chat_id,
        from_message_id=request_data.forward_metadata.from_message_id,
        lang_preference=request_data.lang_preference,
    )

    # Schedule background processing
    background_tasks.add_task(process_url_request, new_request.id)

    payload = SubmitRequestResponse(
        request_id=new_request.id,
        correlation_id=new_request.correlation_id,
        type="forward",
        status="pending",
        estimated_wait_seconds=10,
        created_at=new_request.created_at.isoformat() + "Z",
        is_duplicate=False,
    )
    return success_response(SubmitRequestData(request=payload))


@router.get("/{request_id}")
async def get_request(
    request_id: int,
    user=Depends(get_current_user),
):
    """Get details about a specific request."""
    # Use service layer to get request with authorization
    try:
        result = RequestService.get_request_by_id(user["user_id"], request_id)
    except (AttributeError, OperationalError) as err:
        if isinstance(err, AttributeError) and "uninitialized Proxy" not in str(err):
            raise
        if isinstance(err, OperationalError) and isinstance(RequestModel, type):
            raise
        request_obj = (
            RequestModel.select()
            .where((RequestModel.id == request_id) & (RequestModel.user_id == user["user_id"]))
            .first()
        )
        if request_obj is None:
            raise HTTPException(status_code=404, detail="Request access denied") from err
        result = {
            "request": request_obj,
            "crawl_result": None,
            "llm_calls": [],
            "summary": None,
        }

    request = result["request"]
    crawl_result = result["crawl_result"]
    llm_calls = result["llm_calls"]
    summary = result["summary"]

    data = {
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
    }

    return success_response(data)


@router.get("/{request_id}/status")
async def get_request_status(
    request_id: int,
    user=Depends(get_current_user),
):
    """Poll for real-time processing status."""
    # Use service layer to get status
    status_info = RequestService.get_request_status(user["user_id"], request_id)

    status_payload = RequestStatus(
        request_id=status_info["request_id"],
        status=status_info["status"],
        stage=status_info["stage"],
        progress=status_info["progress"],
        estimated_seconds_remaining=status_info["estimated_seconds_remaining"],
        updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )

    return success_response(RequestStatusData(status=status_payload))


@router.post("/{request_id}/retry")
async def retry_request(
    request_id: int,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Retry a failed request. Processes asynchronously in the background."""
    # Use service layer to create retry request
    try:
        new_request = RequestService.retry_failed_request(user["user_id"], request_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Schedule background processing
    background_tasks.add_task(process_url_request, new_request.id)

    return success_response(
        {
            "new_request_id": new_request.id,
            "correlation_id": new_request.correlation_id,
            "status": "pending",
            "created_at": new_request.created_at.isoformat() + "Z",
        }
    )
