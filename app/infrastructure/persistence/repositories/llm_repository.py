"""SQLAlchemy implementation of the LLM-call repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, func, or_, select

if TYPE_CHECKING:
    from app.application.ports.requests import LLMCallRecord
    from app.db.session import Database

from app.db.json_utils import prepare_json_payload
from app.db.models import LLMCall, Request, model_to_dict


def _build_llm_call_payload(call_data: dict[str, Any] | Any) -> dict[str, Any]:
    """Normalize LLM call payloads for single and batched inserts."""
    provider = call_data.get("provider")
    response_text = call_data.get("response_text")

    headers_payload = prepare_json_payload(call_data.get("request_headers_json"), default={})
    messages_payload = prepare_json_payload(call_data.get("request_messages_json"), default=[])
    response_payload = prepare_json_payload(call_data.get("response_json"), default={})
    error_context_payload = prepare_json_payload(call_data.get("error_context_json"))

    payload = {
        "request_id": call_data.get("request_id"),
        "provider": provider,
        "model": call_data.get("model"),
        "endpoint": call_data.get("endpoint"),
        "request_headers_json": headers_payload,
        "request_messages_json": messages_payload,
        "tokens_prompt": call_data.get("tokens_prompt"),
        "tokens_completion": call_data.get("tokens_completion"),
        "cost_usd": call_data.get("cost_usd"),
        "latency_ms": call_data.get("latency_ms"),
        "status": call_data.get("status"),
        "error_text": call_data.get("error_text"),
        "structured_output_used": call_data.get("structured_output_used"),
        "structured_output_mode": call_data.get("structured_output_mode"),
        "error_context_json": error_context_payload,
    }

    if provider == "openrouter":
        payload["openrouter_response_text"] = response_text
        payload["openrouter_response_json"] = response_payload
        payload["response_text"] = None
        payload["response_json"] = None
    else:
        payload["response_text"] = response_text
        payload["response_json"] = response_payload

    return payload


class LLMRepositoryAdapter:
    """Adapter for LLM call logging operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_insert_llm_call(self, record: LLMCallRecord) -> int:
        """Insert an LLM call log record."""
        async with self._database.transaction() as session:
            call = LLMCall(**_build_llm_call_payload(record))
            session.add(call)
            await session.flush()
            return call.id

    async def async_insert_llm_calls_batch(
        self,
        calls: list[dict[str, Any]],
    ) -> list[int]:
        """Insert multiple LLM calls in a single transaction."""
        if not calls:
            return []

        async with self._database.transaction() as session:
            rows = [LLMCall(**_build_llm_call_payload(call_data)) for call_data in calls]
            session.add_all(rows)
            await session.flush()
            return [row.id for row in rows]

    async def async_get_latest_llm_model_by_request_id(self, request_id: int) -> str | None:
        """Get the latest LLM model used for a request."""
        async with self._database.session() as session:
            return await session.scalar(
                select(LLMCall.model)
                .where(LLMCall.request_id == request_id, LLMCall.model.is_not(None))
                .order_by(LLMCall.id.desc())
                .limit(1)
            )

    async def async_get_llm_calls_by_request(self, request_id: int) -> list[dict[str, Any]]:
        """Get all LLM calls for a request."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(LLMCall).where(LLMCall.request_id == request_id).order_by(LLMCall.id)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def async_count_llm_calls_by_request(self, request_id: int) -> int:
        """Count LLM calls for a request."""
        async with self._database.session() as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(LLMCall)
                    .where(LLMCall.request_id == request_id)
                )
                or 0
            )

    async def async_get_latest_error_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Return the newest error-like LLM call for the request."""
        async with self._database.session() as session:
            row = await session.scalar(
                select(LLMCall)
                .where(
                    LLMCall.request_id == request_id,
                    or_(
                        LLMCall.status == "error",
                        LLMCall.error_text.is_not(None),
                        LLMCall.error_context_json.is_not(None),
                    ),
                )
                .order_by(desc(LLMCall.updated_at), desc(LLMCall.id))
                .limit(1)
            )
            return model_to_dict(row)

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version across LLM calls owned by *user_id*."""
        async with self._database.session() as session:
            value = await session.scalar(
                select(func.max(LLMCall.server_version))
                .join(Request, LLMCall.request_id == Request.id)
                .where(Request.user_id == user_id)
            )
            return int(value) if value is not None else None

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all LLM calls for a user, with request_id flattened."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(LLMCall)
                    .join(Request, LLMCall.request_id == Request.id)
                    .where(Request.user_id == user_id)
                    .order_by(LLMCall.id)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]
