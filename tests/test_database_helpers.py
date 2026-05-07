from __future__ import annotations

import copy
import shutil
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, update

from app.db.models import LLMCall, Request, Summary, TelegramMessage
from tests.db_helpers_async import (
    create_request,
    get_crawl_result_by_request,
    get_request_by_dedupe_hash,
    get_summary_by_request,
    insert_audit_log,
    insert_crawl_result,
    insert_llm_call,
    insert_summary,
    insert_telegram_message,
    update_request_status,
    upsert_summary,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.session import Database


HAS_PG_DUMP = shutil.which("pg_dump") is not None
PG_DUMP_REASON = (
    "create_backup_copy delegates to pg_dump (host or docker exec). "
    "Skip when neither is available in the test environment."
)


@pytest.mark.skipif(not HAS_PG_DUMP, reason=PG_DUMP_REASON)
def test_create_backup_copy_writes_dump(database: Database, tmp_path) -> None:
    backup_path = tmp_path / "backups" / "snapshot.dump"

    created = database.create_backup_copy(str(backup_path))

    assert created.exists()
    assert created.suffix == ".dump"
    assert created.stat().st_size > 0


async def test_create_request_and_fetch_by_hash(session: AsyncSession) -> None:
    rid = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id="abc123",
        chat_id=100,
        user_id=200,
        input_url="https://example.com",
        normalized_url="https://example.com",
        dedupe_hash="abc",
        route_version=1,
    )
    assert isinstance(rid, int)
    row = await get_request_by_dedupe_hash(session, "abc")
    assert row is not None
    assert row["id"] == rid
    assert row["status"] == "pending"
    assert row["correlation_id"] == "abc123"

    await update_request_status(session, rid, "ok")
    await session.execute(
        update(Request).where(Request.id == rid).values(lang_detected="en", correlation_id="zzz999")
    )

    row2 = await get_request_by_dedupe_hash(session, "abc")
    assert row2 is not None
    assert row2["status"] == "ok"
    assert row2["lang_detected"] == "en"
    assert row2["correlation_id"] == "zzz999"


async def test_create_request_handles_duplicate_hash_race(session: AsyncSession) -> None:
    first_id = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id="cid-1",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/path",
        normalized_url="https://example.com/path",
        dedupe_hash="shared-hash",
        route_version=1,
    )

    second_id = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id="cid-2",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/path",
        normalized_url="https://example.com/path",
        dedupe_hash="shared-hash",
        route_version=1,
    )

    assert first_id == second_id

    row = await get_request_by_dedupe_hash(session, "shared-hash")
    assert row is not None
    assert row["id"] == first_id
    # Latest correlation id should be persisted
    assert row["correlation_id"] == "cid-2"

    # Only one record should exist
    count = await session.scalar(
        select(func.count()).select_from(Request).where(Request.dedupe_hash == "shared-hash")
    )
    assert count == 1


async def test_crawl_result_helpers(session: AsyncSession) -> None:
    rid = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id=None,
        chat_id=None,
        user_id=None,
        normalized_url="https://example.com/crawl-test",
        route_version=1,
    )
    cid = await insert_crawl_result(
        session,
        request_id=rid,
        source_url="https://example.com",
        endpoint="/v2/scrape",
        http_status=200,
        status="ok",
        options_json={},
        correlation_id="fc-123",
        content_markdown="# md",
        content_html=None,
        structured_json={},
        metadata_json={},
        links_json={},
        screenshots_paths_json=None,
        firecrawl_success=True,
        firecrawl_error_code=None,
        firecrawl_error_message=None,
        firecrawl_details_json=None,
        raw_response_json=None,
        latency_ms=123,
        error_text=None,
    )
    assert isinstance(cid, int)
    row = await get_crawl_result_by_request(session, rid)
    assert row is not None
    assert row["http_status"] == 200
    assert row["content_markdown"] == "# md"
    assert row["correlation_id"] == "fc-123"
    assert row["firecrawl_success"]
    assert row["raw_response_json"] is None


async def test_summary_upsert(session: AsyncSession) -> None:
    rid = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id=None,
        chat_id=None,
        user_id=None,
        normalized_url="https://example.com/upsert-test",
        route_version=1,
    )
    v1 = await upsert_summary(session, request_id=rid, lang="en", json_payload={"a": 1})
    assert v1 >= 1
    row = await get_summary_by_request(session, rid)
    assert row is not None
    assert row["version"] == v1
    assert row["lang"] == "en"
    assert row["insights_json"] is None

    v2 = await upsert_summary(session, request_id=rid, lang="en", json_payload={"a": 2})
    assert v2 > v1
    row2 = await get_summary_by_request(session, rid)
    assert row2 is not None
    assert row2["version"] == v2

    insights_payload = {"topic_overview": "Context", "new_facts": []}
    await session.execute(
        update(Summary).where(Summary.request_id == rid).values(insights_json=insights_payload)
    )
    row3 = await get_summary_by_request(session, rid)
    assert row3 is not None
    assert row3["insights_json"] == insights_payload


async def test_insert_llm_and_telegram_and_audit(session: AsyncSession) -> None:
    rid = await create_request(
        session,
        type_="forward",
        status="pending",
        correlation_id=None,
        chat_id=1,
        user_id=2,
        route_version=1,
    )
    # Telegram message
    mid = await insert_telegram_message(
        session,
        request_id=rid,
        message_id=10,
        chat_id=1,
        date_ts=1700000000,
        text_full="hello",
        entities_json=[{"type": "bold"}],
        media_type="photo",
        media_file_ids_json=["file_1"],
        forward_from_chat_id=7,
        forward_from_chat_type="channel",
        forward_from_chat_title="Title",
        forward_from_message_id=5,
        forward_date_ts=1700000001,
        telegram_raw_json={"k": "v"},
    )
    assert isinstance(mid, int)
    tg_row = await session.scalar(
        select(TelegramMessage).where(TelegramMessage.request_id == rid)
    )
    assert tg_row is not None
    assert tg_row.media_type == "photo"
    assert tg_row.chat_id == 1

    # LLM call
    lid = await insert_llm_call(
        session,
        request_id=rid,
        provider="openrouter",
        model="m",
        endpoint="/api/v1/chat/completions",
        request_headers_json={"Authorization": "REDACTED"},
        request_messages_json=[{"role": "user", "content": "hi"}],
        response_text="{}",
        response_json={"choices": []},
        tokens_prompt=1,
        tokens_completion=2,
        cost_usd=0.001,
        latency_ms=50,
        status="ok",
        error_text=None,
        structured_output_used=True,
        structured_output_mode="json_schema",
        error_context_json={"status_code": 200},
    )
    assert isinstance(lid, int)
    llm_row = await session.scalar(select(LLMCall).where(LLMCall.id == lid))
    assert llm_row is not None
    assert llm_row.status == "ok"
    assert llm_row.tokens_completion == 2
    assert llm_row.structured_output_used is True
    assert llm_row.structured_output_mode == "json_schema"
    assert llm_row.error_context_json == {"status_code": 200}
    # Provider-specific routing: openrouter responses live in dedicated columns
    assert llm_row.response_text is None
    assert llm_row.response_json is None
    assert llm_row.openrouter_response_text == "{}"
    assert llm_row.openrouter_response_json == {"choices": []}

    # Audit
    aid = await insert_audit_log(session, level="INFO", event="test", details_json={"x": 1})
    assert isinstance(aid, int)
    from app.db.models import AuditLog

    audit_row = await session.scalar(select(AuditLog).where(AuditLog.id == aid))
    assert audit_row is not None
    assert audit_row.level == "INFO"


@pytest.mark.xfail(
    reason=(
        "DatabaseInspectionService.async_verify_processing_integrity is a stub: it "
        "returns {errors: ['processing integrity SQLAlchemy port is tracked in R3']} "
        "instead of doing the real walk. The peewee implementation was not ported. "
        "Re-enable this test when R3 (processing-integrity SQLAlchemy port) lands."
    ),
    strict=True,
)
async def test_verify_processing_integrity(
    session: AsyncSession, database: Database
) -> None:
    base_summary = {
        "summary_250": "Short summary.",
        "summary_1000": "Medium summary providing additional detail.",
        "tldr": "Longer summary text.",
        "key_ideas": ["Idea"],
        "topic_tags": ["#tag"],
        "entities": {
            "people": [],
            "organizations": [],
            "locations": [],
        },
        "estimated_reading_time_min": 5,
        "key_stats": [],
        "answered_questions": [],
        "readability": {"method": "FK", "score": 50.0, "level": "Standard"},
        "seo_keywords": [],
        "metadata": {
            "title": "Title",
            "canonical_url": "https://example.com/article",
            "domain": "example.com",
            "author": "Author",
            "published_at": "2024-01-01",
            "last_updated": "2024-01-01",
        },
        "extractive_quotes": [],
        "highlights": [],
        "questions_answered": [],
        "categories": [],
        "topic_taxonomy": [],
        "hallucination_risk": "low",
        "confidence": 1.0,
        "forwarded_post_extras": None,
        "key_points_to_remember": [],
    }

    rid_good = await create_request(
        session,
        type_="url",
        status="ok",
        correlation_id="good",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/good",
        normalized_url="https://example.com/good",
        route_version=1,
    )
    await insert_summary(
        session,
        request_id=rid_good,
        lang="en",
        json_payload=base_summary,
    )
    await insert_crawl_result(
        session,
        request_id=rid_good,
        source_url="https://example.com/good",
        endpoint="/v2/scrape",
        http_status=200,
        status="ok",
        options_json={},
        correlation_id="fc-good",
        content_markdown="# md",
        content_html=None,
        structured_json={},
        metadata_json={},
        links_json=["https://example.com/other"],
        screenshots_paths_json=None,
        firecrawl_success=True,
        firecrawl_error_code=None,
        firecrawl_error_message=None,
        firecrawl_details_json=None,
        raw_response_json=None,
        latency_ms=100,
        error_text=None,
    )

    bad_summary = copy.deepcopy(base_summary)
    bad_summary.pop("summary_1000", None)
    bad_summary.pop("tldr", None)
    bad_summary["summary_250"] = ""
    bad_summary.pop("metadata", None)

    rid_bad = await create_request(
        session,
        type_="url",
        status="ok",
        correlation_id="bad",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/bad",
        normalized_url="https://example.com/bad",
        route_version=1,
    )
    await insert_summary(
        session,
        request_id=rid_bad,
        lang="en",
        json_payload=bad_summary,
    )

    rid_empty_links = await create_request(
        session,
        type_="url",
        status="ok",
        correlation_id="empty",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/empty",
        normalized_url="https://example.com/empty",
        route_version=1,
    )
    await insert_summary(
        session,
        request_id=rid_empty_links,
        lang="en",
        json_payload=base_summary,
    )
    await insert_crawl_result(
        session,
        request_id=rid_empty_links,
        source_url="https://example.com/empty",
        endpoint="/v2/scrape",
        http_status=200,
        status="ok",
        options_json={},
        correlation_id="fc-empty",
        content_markdown="# md",
        content_html=None,
        structured_json={},
        metadata_json={},
        links_json=[],
        screenshots_paths_json=None,
        firecrawl_success=True,
        firecrawl_error_code=None,
        firecrawl_error_message=None,
        firecrawl_details_json=None,
        raw_response_json=None,
        latency_ms=100,
        error_text=None,
    )

    rid_missing = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id="missing",
        chat_id=1,
        user_id=1,
        input_url="https://example.com/missing",
        normalized_url="https://example.com/missing",
        route_version=1,
    )

    # Flush the test's pending writes so verify_processing_integrity (which
    # opens its own short-lived session) sees them.
    await session.commit()

    # Use the async API directly: the sync wrapper exposed on Database refuses
    # to run inside an active event loop.
    verification = await database._inspection.async_verify_processing_integrity()

    assert "overview" in verification
    posts = verification.get("posts")
    assert isinstance(posts, dict)
    overview = verification.get("overview")
    assert isinstance(overview, dict)
    assert posts.get("checked") == 4
    assert posts.get("with_summary") == 3
    assert overview.get("total_requests") == 4
    assert overview.get("total_summaries") == 3

    missing_summary = posts.get("missing_summary") or []
    assert len(missing_summary) == 1
    assert missing_summary[0]["request_id"] == rid_missing

    missing_fields = posts.get("missing_fields") or []
    bad_entries = [entry for entry in missing_fields if entry.get("request_id") == rid_bad]
    assert bad_entries
    bad_missing = bad_entries[0].get("missing") or []
    assert "summary_250" in bad_missing
    assert "summary_1000" in bad_missing
    assert "tldr" in bad_missing
    assert "metadata" in bad_missing

    links_info = posts.get("links") or {}
    assert links_info.get("total_links") == 2
    assert links_info.get("posts_with_links") == 4
    missing_links = links_info.get("missing_data") or []
    missing_map = {entry.get("request_id"): entry for entry in missing_links}
    assert rid_bad in missing_map
    assert missing_map[rid_bad].get("reason") == "absent_links_json"
    assert rid_missing in missing_map
    assert missing_map[rid_missing].get("reason") == "absent_links_json"

    reprocess_entries = posts.get("reprocess") or []
    assert len(reprocess_entries) == 2
    reprocess_map = {
        entry.get("request_id"): set(entry.get("reasons") or []) for entry in reprocess_entries
    }
    assert rid_bad in reprocess_map
    assert "missing_fields" in reprocess_map[rid_bad]
    assert "missing_links" in reprocess_map[rid_bad]
    assert rid_missing in reprocess_map
    assert "missing_summary" in reprocess_map[rid_missing]
    assert "missing_links" in reprocess_map[rid_missing]
    assert rid_empty_links not in reprocess_map


async def test_insert_telegram_message_handles_duplicate_request(
    session: AsyncSession,
) -> None:
    rid = await create_request(
        session,
        type_="url",
        status="pending",
        correlation_id="cid-telegram",
        chat_id=1,
        user_id=2,
        input_url="https://example.org",
        normalized_url="https://example.org",
        dedupe_hash="telegram-dup",
        route_version=1,
    )

    mid1 = await insert_telegram_message(
        session,
        request_id=rid,
        message_id=10,
        chat_id=1,
        date_ts=1700000000,
        text_full="hello",
        entities_json=[{"type": "bold"}],
        media_type="photo",
        media_file_ids_json=["file_a"],
        forward_from_chat_id=None,
        forward_from_chat_type=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        forward_date_ts=None,
        telegram_raw_json={"k": "v"},
    )

    mid2 = await insert_telegram_message(
        session,
        request_id=rid,
        message_id=10,
        chat_id=1,
        date_ts=1700000000,
        text_full="hello",
        entities_json=[{"type": "bold"}],
        media_type="video",
        media_file_ids_json=["file_b"],
        forward_from_chat_id=None,
        forward_from_chat_type=None,
        forward_from_chat_title=None,
        forward_from_message_id=None,
        forward_date_ts=None,
        telegram_raw_json={"k": "v"},
    )

    assert mid1 == mid2

    row = await session.scalar(
        select(TelegramMessage).where(TelegramMessage.request_id == rid)
    )
    assert row is not None
    # The original payload should remain intact
    assert row.media_type == "photo"
    assert row.media_file_ids_json == ["file_a"]
