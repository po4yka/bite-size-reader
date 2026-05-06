"""Standalone test helper functions for database operations.

These replicate the sync CRUD helpers that were previously available as mixin
methods on the deprecated ``Database`` facade.  They operate on Peewee models
directly via the already-initialized ``database_proxy``.

NOTE: The SQLAlchemy ORM models in ``app.db.models`` no longer export
``database_proxy`` or Peewee model classes.  These helpers instead import from
the frozen Peewee snapshot in ``app.cli._legacy_peewee_models`` which is kept
specifically for tests and CLI migration tooling during the SQLite→Postgres
migration.  When that migration is complete these helpers should be ported to
async SQLAlchemy and this import should be updated.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

import peewee

from app.cli._legacy_peewee_models import (
    AuditLog,
    Chat,
    CrawlResult,
    LLMCall,
    Request,
    Summary,
    TelegramMessage,
    User,
    UserInteraction,
    database_proxy,
    model_to_dict,
)
from app.core.time_utils import UTC
from app.db.json_utils import prepare_json_payload

JSONValue = Mapping[str, Any] | list[Any] | tuple[Any, ...] | str | None


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def create_request(
    *,
    type_: str,
    status: str,
    correlation_id: str | None = None,
    chat_id: int | None = None,
    user_id: int | None = None,
    input_url: str | None = None,
    normalized_url: str | None = None,
    dedupe_hash: str | None = None,
    input_message_id: int | None = None,
    fwd_from_chat_id: int | None = None,
    fwd_from_msg_id: int | None = None,
    lang_detected: str | None = None,
    content_text: str | None = None,
    route_version: int = 1,
) -> int:
    try:
        request = Request.create(
            type=type_,
            status=status,
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_url=input_url,
            normalized_url=normalized_url,
            dedupe_hash=dedupe_hash,
            input_message_id=input_message_id,
            fwd_from_chat_id=fwd_from_chat_id,
            fwd_from_msg_id=fwd_from_msg_id,
            lang_detected=lang_detected,
            content_text=content_text,
            route_version=route_version,
        )
        return request.id
    except peewee.IntegrityError:
        if dedupe_hash:
            Request.update(
                {
                    Request.correlation_id: correlation_id,
                    Request.status: status,
                    Request.chat_id: chat_id,
                    Request.user_id: user_id,
                    Request.input_url: input_url,
                    Request.normalized_url: normalized_url,
                    Request.input_message_id: input_message_id,
                    Request.fwd_from_chat_id: fwd_from_chat_id,
                    Request.fwd_from_msg_id: fwd_from_msg_id,
                    Request.lang_detected: lang_detected,
                    Request.content_text: content_text,
                    Request.route_version: route_version,
                }
            ).where(Request.dedupe_hash == dedupe_hash).execute()
            existing = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
            if existing:
                return existing.id
        raise


def get_request_by_dedupe_hash(dedupe_hash: str) -> dict[str, Any] | None:
    request = Request.get_or_none(Request.dedupe_hash == dedupe_hash)
    return model_to_dict(request)


def get_request_by_forward(fwd_chat_id: int, fwd_msg_id: int) -> dict[str, Any] | None:
    request = Request.get_or_none(
        (Request.fwd_from_chat_id == fwd_chat_id) & (Request.fwd_from_msg_id == fwd_msg_id)
    )
    return model_to_dict(request)


def update_request_status(request_id: int, status: str) -> None:
    Request.update({Request.status: status}).where(Request.id == request_id).execute()


def get_crawl_result_by_request(request_id: int) -> dict[str, Any] | None:
    result = CrawlResult.get_or_none(CrawlResult.request == request_id)
    data = model_to_dict(result)
    if data:
        _convert_bool_fields(data, ["firecrawl_success"])
    return data


# ---------------------------------------------------------------------------
# Crawl / Telegram / LLM helpers
# ---------------------------------------------------------------------------


def insert_crawl_result(
    *,
    request_id: int,
    source_url: str | None = None,
    endpoint: str | None = None,
    http_status: int | None = None,
    status: str | None = None,
    options_json: JSONValue = None,
    correlation_id: str | None = None,
    content_markdown: str | None = None,
    content_html: str | None = None,
    structured_json: JSONValue = None,
    metadata_json: JSONValue = None,
    links_json: JSONValue = None,
    screenshots_paths_json: JSONValue = None,
    firecrawl_success: bool | None = None,
    firecrawl_error_code: str | None = None,
    firecrawl_error_message: str | None = None,
    firecrawl_details_json: JSONValue = None,
    raw_response_json: JSONValue = None,
    latency_ms: int | None = None,
    error_text: str | None = None,
) -> int:
    try:
        result = CrawlResult.create(
            request=request_id,
            source_url=source_url,
            endpoint=endpoint,
            http_status=http_status,
            status=status,
            options_json=prepare_json_payload(options_json, default={}),
            correlation_id=correlation_id,
            content_markdown=content_markdown,
            content_html=content_html,
            structured_json=prepare_json_payload(structured_json, default={}),
            metadata_json=prepare_json_payload(metadata_json, default={}),
            links_json=prepare_json_payload(links_json, default={}),
            screenshots_paths_json=prepare_json_payload(screenshots_paths_json),
            firecrawl_success=firecrawl_success,
            firecrawl_error_code=firecrawl_error_code,
            firecrawl_error_message=firecrawl_error_message,
            firecrawl_details_json=prepare_json_payload(firecrawl_details_json),
            raw_response_json=prepare_json_payload(raw_response_json),
            latency_ms=latency_ms,
            error_text=error_text,
        )
        return result.id
    except peewee.IntegrityError:
        existing = CrawlResult.get_or_none(CrawlResult.request == request_id)
        if existing:
            return existing.id
        raise


def insert_telegram_message(
    *,
    request_id: int,
    message_id: int | None = None,
    chat_id: int | None = None,
    date_ts: int | None = None,
    text_full: str | None = None,
    entities_json: JSONValue = None,
    media_type: str | None = None,
    media_file_ids_json: JSONValue = None,
    forward_from_chat_id: int | None = None,
    forward_from_chat_type: str | None = None,
    forward_from_chat_title: str | None = None,
    forward_from_message_id: int | None = None,
    forward_date_ts: int | None = None,
    telegram_raw_json: JSONValue = None,
) -> int:
    try:
        message = TelegramMessage.create(
            request=request_id,
            message_id=message_id,
            chat_id=chat_id,
            date_ts=date_ts,
            text_full=text_full,
            entities_json=prepare_json_payload(entities_json),
            media_type=media_type,
            media_file_ids_json=prepare_json_payload(media_file_ids_json),
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_type=forward_from_chat_type,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            forward_date_ts=forward_date_ts,
            telegram_raw_json=prepare_json_payload(telegram_raw_json),
        )
        return message.id
    except peewee.IntegrityError:
        existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
        if existing:
            return existing.id
        raise


def insert_llm_call(
    *,
    request_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
    request_headers_json: JSONValue = None,
    request_messages_json: JSONValue = None,
    response_text: str | None = None,
    response_json: JSONValue = None,
    tokens_prompt: int | None = None,
    tokens_completion: int | None = None,
    cost_usd: float | None = None,
    latency_ms: int | None = None,
    status: str | None = None,
    error_text: str | None = None,
    structured_output_used: bool | None = None,
    structured_output_mode: str | None = None,
    error_context_json: JSONValue = None,
) -> int:
    headers_payload = prepare_json_payload(request_headers_json, default={})
    messages_payload = prepare_json_payload(request_messages_json, default=[])
    response_payload = prepare_json_payload(response_json, default={})
    error_context_payload = prepare_json_payload(error_context_json)
    payload: dict[Any, Any] = {
        LLMCall.request: request_id,
        LLMCall.provider: provider,
        LLMCall.model: model,
        LLMCall.endpoint: endpoint,
        LLMCall.request_headers_json: headers_payload,
        LLMCall.request_messages_json: messages_payload,
        LLMCall.tokens_prompt: tokens_prompt,
        LLMCall.tokens_completion: tokens_completion,
        LLMCall.cost_usd: cost_usd,
        LLMCall.latency_ms: latency_ms,
        LLMCall.status: status,
        LLMCall.error_text: error_text,
        LLMCall.structured_output_used: structured_output_used,
        LLMCall.structured_output_mode: structured_output_mode,
        LLMCall.error_context_json: error_context_payload,
    }
    if provider == "openrouter":
        payload[LLMCall.openrouter_response_text] = response_text
        payload[LLMCall.openrouter_response_json] = response_payload
        payload[LLMCall.response_text] = None
        payload[LLMCall.response_json] = None
    else:
        payload[LLMCall.response_text] = response_text
        payload[LLMCall.response_json] = response_payload

    call = LLMCall.create(**{field.name: value for field, value in payload.items()})
    return call.id


# ---------------------------------------------------------------------------
# User / Chat helpers
# ---------------------------------------------------------------------------


def upsert_user(
    *, telegram_user_id: int, username: str | None = None, is_owner: bool = False
) -> None:
    User.insert(
        telegram_user_id=telegram_user_id,
        username=username,
        is_owner=is_owner,
    ).on_conflict(
        conflict_target=[User.telegram_user_id],
        update={"username": username, "is_owner": is_owner},
    ).execute()


def upsert_chat(
    *,
    chat_id: int,
    type_: str,
    title: str | None = None,
    username: str | None = None,
) -> None:
    Chat.insert(
        chat_id=chat_id,
        type=type_,
        title=title,
        username=username,
    ).on_conflict(
        conflict_target=[Chat.chat_id],
        update={
            "type": type_,
            "title": title,
            "username": username,
        },
    ).execute()


def update_user_interaction(
    interaction_id: int,
    *,
    updates: Mapping[str, Any] | None = None,
    response_sent: bool | None = None,
    response_type: str | None = None,
    error_occurred: bool | None = None,
    error_message: str | None = None,
    processing_time_ms: int | None = None,
    request_id: int | None = None,
) -> None:
    legacy_fields = (
        response_sent,
        response_type,
        error_occurred,
        error_message,
        processing_time_ms,
        request_id,
    )
    if updates and any(f is not None for f in legacy_fields):
        msg = "Cannot mix explicit field arguments with the updates mapping"
        raise ValueError(msg)

    update_values: dict[Any, Any] = {}
    if updates:
        invalid_fields = [
            key
            for key in updates
            if not isinstance(getattr(UserInteraction, key, None), peewee.Field)
        ]
        if invalid_fields:
            msg = f"Unknown user interaction fields: {', '.join(invalid_fields)}"
            raise ValueError(msg)
        for key, value in updates.items():
            field_obj = getattr(UserInteraction, key)
            update_values[field_obj] = value

    if response_sent is not None:
        update_values[UserInteraction.response_sent] = response_sent
    if response_type is not None:
        update_values[UserInteraction.response_type] = response_type
    if error_occurred is not None:
        update_values[UserInteraction.error_occurred] = error_occurred
    if error_message is not None:
        update_values[UserInteraction.error_message] = error_message
    if processing_time_ms is not None:
        update_values[UserInteraction.processing_time_ms] = processing_time_ms
    if request_id is not None:
        update_values[UserInteraction.request] = request_id

    if not update_values:
        return

    updated_at_field = getattr(UserInteraction, "updated_at", None)
    if isinstance(updated_at_field, peewee.Field):
        try:
            columns = {
                column.name
                for column in database_proxy.get_columns(UserInteraction._meta.table_name)
            }
        except (peewee.DatabaseError, AttributeError):
            columns = set()
        if updated_at_field.column_name in columns:
            update_values[updated_at_field] = dt.datetime.now(UTC)

    UserInteraction.update(update_values).where(UserInteraction.id == interaction_id).execute()


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def insert_summary(
    *,
    request_id: int,
    lang: str | None = None,
    json_payload: JSONValue = None,
    insights_json: JSONValue = None,
    version: int = 1,
    is_read: bool = False,
) -> int:
    summary = Summary.create(
        request=request_id,
        lang=lang,
        json_payload=prepare_json_payload(json_payload),
        insights_json=prepare_json_payload(insights_json),
        version=version,
        is_read=is_read,
    )
    return summary.id


def upsert_summary(
    *,
    request_id: int,
    lang: str | None = None,
    json_payload: JSONValue = None,
    insights_json: JSONValue = None,
    is_read: bool | None = None,
) -> int:
    payload_value = prepare_json_payload(json_payload)
    insights_value = prepare_json_payload(insights_json)
    try:
        summary = Summary.create(
            request=request_id,
            lang=lang,
            json_payload=payload_value,
            insights_json=insights_value,
            version=1,
            is_read=is_read if is_read is not None else False,
        )
        return summary.version
    except peewee.IntegrityError:
        update_map: dict[Any, Any] = {
            Summary.lang: lang,
            Summary.json_payload: payload_value,
            Summary.version: Summary.version + 1,
            Summary.created_at: dt.datetime.now(UTC),
        }
        if insights_value is not None:
            update_map[Summary.insights_json] = insights_value
        if is_read is not None:
            update_map[Summary.is_read] = is_read
        Summary.update(update_map).where(Summary.request == request_id).execute()
        updated = Summary.get_or_none(Summary.request == request_id)
        return updated.version if updated else 0


def get_summary_by_request(request_id: int) -> dict[str, Any] | None:
    summary = Summary.get_or_none(Summary.request == request_id)
    data = model_to_dict(summary)
    if data:
        _convert_bool_fields(data, ["is_read"])
    return data


def get_read_status(request_id: int) -> bool:
    summary = Summary.get_or_none(Summary.request == request_id)
    return bool(summary.is_read) if summary else False


def mark_summary_as_read(request_id: int) -> None:
    Summary.update({Summary.is_read: True}).where(Summary.request == request_id).execute()


def get_unread_summaries(
    *,
    user_id: int | None = None,
    chat_id: int | None = None,
    limit: int = 10,
    topic: str | None = None,
) -> list[dict[str, Any]]:
    """Return unread summary rows filtered by owner/chat/topic constraints."""
    from app.application.services.topic_search_utils import ensure_mapping, summary_matches_topic

    if limit <= 0:
        return []

    topic_query = topic.strip() if topic else None
    base_query = (
        Summary.select(Summary, Request)
        .join(Request)
        .where(~Summary.is_read)
        .order_by(Summary.created_at.asc())
    )

    if user_id is not None:
        base_query = base_query.where(
            (Request.user_id == user_id) | (Request.user_id.is_null(True))
        )
    if chat_id is not None:
        base_query = base_query.where(
            (Request.chat_id == chat_id) | (Request.chat_id.is_null(True))
        )

    fetch_limit: int | None = limit
    if topic_query:
        fetch_limit = None  # fetch all and filter in-memory

    rows_query = base_query
    if fetch_limit is not None:
        rows_query = base_query.limit(fetch_limit)

    results: list[dict[str, Any]] = []
    for row in rows_query:
        payload = ensure_mapping(row.json_payload)
        request_data = model_to_dict(row.request) or {}

        if topic_query and not summary_matches_topic(payload, request_data, topic_query):
            continue

        data = model_to_dict(row) or {}
        req_data = request_data
        req_data.pop("id", None)
        data.update(req_data)
        if "request" in data and "request_id" not in data:
            data["request_id"] = data["request"]
        _convert_bool_fields(data, ["is_read"])
        results.append(data)
        if len(results) >= limit:
            break
    return results


def get_unread_summary_by_request_id(request_id: int) -> dict[str, Any] | None:
    """Get a specific unread summary by request ID."""
    summary = (
        Summary.select(Summary, Request)
        .join(Request)
        .where((Summary.request == request_id) & (~Summary.is_read))
        .first()
    )
    if not summary:
        return None
    data = model_to_dict(summary) or {}
    req_data = model_to_dict(summary.request) or {}
    req_data.pop("id", None)
    data.update(req_data)
    if "request" in data and "request_id" not in data:
        data["request_id"] = data["request"]
    _convert_bool_fields(data, ["is_read"])
    return data


def get_user_interactions(*, uid: int, limit: int = 10) -> list[dict[str, Any]]:
    """Get recent user interactions for a user."""
    interactions = (
        UserInteraction.select()
        .where(UserInteraction.user_id == uid)
        .order_by(UserInteraction.created_at.desc())
        .limit(limit)
    )
    return [model_to_dict(interaction) for interaction in interactions]


def insert_audit_log(
    *,
    level: str,
    event: str,
    details_json: JSONValue = None,
) -> int:
    entry = AuditLog.create(
        level=level,
        event=event,
        details_json=prepare_json_payload(details_json),
    )
    return entry.id


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _convert_bool_fields(data: dict[str, Any], fields: list[str]) -> None:
    for field_name in fields:
        if field_name in data and data[field_name] is not None:
            data[field_name] = int(bool(data[field_name]))
