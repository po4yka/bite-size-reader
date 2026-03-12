from __future__ import annotations

import pytest

from app.api.exceptions import DuplicateResourceError, ResourceNotFoundError
from app.api.services.request_service import RequestService
from app.db.models import CrawlResult, LLMCall, Request, Summary


@pytest.mark.asyncio
async def test_create_url_request_and_duplicate_detection(db, user_factory) -> None:
    user = user_factory(username="request-user", telegram_user_id=5001)

    created = await RequestService.create_url_request(
        user.telegram_user_id,
        "example.com/articles/123",
        lang_preference="en",
    )

    Summary.create(
        request=created.id,
        lang="en",
        json_payload={
            "tldr": "TLDR",
            "summary_250": "Summary text",
            "key_ideas": ["idea"],
        },
    )

    duplicate = await RequestService.check_duplicate_url(
        user.telegram_user_id,
        "example.com/articles/123",
    )

    assert created.type == "url"
    assert created.normalized_url == "http://example.com/articles/123"
    assert duplicate["existing_request_id"] == created.id
    assert duplicate["existing_summary_id"] is not None

    with pytest.raises(DuplicateResourceError):
        await RequestService.create_url_request(user.telegram_user_id, "example.com/articles/123")


@pytest.mark.asyncio
async def test_create_forward_request_and_get_request_by_id_with_related_records(
    db,
    user_factory,
) -> None:
    user = user_factory(username="forward-user", telegram_user_id=5002)
    request = await RequestService.create_forward_request(
        user.telegram_user_id,
        "Forwarded content",
        from_chat_id=111,
        from_message_id=222,
        lang_preference="ru",
    )

    CrawlResult.create(
        request=request.id,
        status="ok",
        source_url="https://example.com/post",
    )
    LLMCall.create(request=request.id, status="ok", response_text="LLM output")
    Summary.create(
        request=request.id,
        lang="ru",
        json_payload={"tldr": "TLDR", "summary_250": "Summary", "key_ideas": ["idea"]},
    )

    details = await RequestService.get_request_by_id(user.telegram_user_id, request.id)

    assert details["request"].id == request.id
    assert details["crawl_result"].source_url == "https://example.com/post"
    assert len(details["llm_calls"]) == 1
    assert details["summary"].lang == "ru"

    with pytest.raises(ResourceNotFoundError):
        await RequestService.get_request_by_id(9999, request.id)


@pytest.mark.asyncio
async def test_retry_failed_request_requires_error_status_and_copies_fields(
    db, user_factory
) -> None:
    user = user_factory(username="retry-user", telegram_user_id=5003)
    failed = Request.create(
        user_id=user.telegram_user_id,
        input_url="https://retry.example.com",
        normalized_url="https://retry.example.com",
        dedupe_hash="hash-1",
        content_text="payload",
        fwd_from_chat_id=333,
        fwd_from_msg_id=444,
        lang_detected="en",
        correlation_id="cid-1",
        status="error",
        type="url",
    )

    retried = await RequestService.retry_failed_request(user.telegram_user_id, failed.id)

    assert retried.status == "pending"
    assert retried.input_url == failed.input_url
    assert retried.correlation_id == "cid-1-retry-1"

    pending = Request.create(
        user_id=user.telegram_user_id,
        input_url="https://pending.example.com",
        normalized_url="https://pending.example.com",
        status="pending",
        type="url",
    )

    with pytest.raises(ValueError, match="Only failed requests"):
        await RequestService.retry_failed_request(user.telegram_user_id, pending.id)
