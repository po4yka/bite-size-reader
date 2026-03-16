"""SQLite implementation of LLM repository.

This adapter handles logging and retrieval of LLM call data.
"""

from __future__ import annotations

from typing import Any

import peewee

from app.db.models import LLMCall, model_to_dict
from app.db.utils import prepare_json_payload
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


def _build_llm_call_payload(call_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM call payloads for single and batched inserts."""
    provider = call_data.get("provider")
    response_text = call_data.get("response_text")

    headers_payload = prepare_json_payload(call_data.get("request_headers_json"), default={})
    messages_payload = prepare_json_payload(call_data.get("request_messages_json"), default=[])
    response_payload = prepare_json_payload(call_data.get("response_json"), default={})
    error_context_payload = prepare_json_payload(call_data.get("error_context_json"))

    payload = {
        "request": call_data.get("request_id"),
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


class SqliteLLMRepositoryAdapter(SqliteBaseRepository):
    """Adapter for LLM call logging operations."""

    async def async_insert_llm_call(self, **kwargs: Any) -> int:
        """Insert an LLM call log record."""

        def _insert() -> int:
            call = LLMCall.create(**_build_llm_call_payload(kwargs))
            return call.id

        return await self._execute(_insert, operation_name="insert_llm_call")

    async def async_insert_llm_calls_batch(
        self,
        calls: list[dict[str, Any]],
    ) -> list[int]:
        """Insert multiple LLM calls in a single transaction."""
        if not calls:
            return []

        def _insert() -> list[int]:
            call_ids: list[int] = []
            for call_data in calls:
                call = LLMCall.create(**_build_llm_call_payload(call_data))
                call_ids.append(call.id)
            return call_ids

        return await self._execute_transaction(
            _insert,
            operation_name="insert_llm_calls_batch",
        )

    async def async_get_latest_llm_model_by_request_id(self, request_id: int) -> str | None:
        """Get the latest LLM model used for a request."""

        def _get() -> str | None:
            call = (
                LLMCall.select(LLMCall.model)
                .where(LLMCall.request == request_id, LLMCall.model.is_null(False))
                .order_by(LLMCall.id.desc())
                .first()
            )
            return call.model if call else None

        return await self._execute(
            _get, operation_name="get_latest_llm_model_by_request_id", read_only=True
        )

    async def async_get_llm_calls_by_request(self, request_id: int) -> list[dict[str, Any]]:
        """Get all LLM calls for a request."""

        def _get() -> list[dict[str, Any]]:
            calls = LLMCall.select().where(LLMCall.request == request_id)
            return [model_to_dict(call) or {} for call in calls]

        return await self._execute(_get, operation_name="get_llm_calls_by_request", read_only=True)

    async def async_count_llm_calls_by_request(self, request_id: int) -> int:
        """Count LLM calls for a request."""

        def _count() -> int:
            return LLMCall.select().where(LLMCall.request == request_id).count()

        return await self._execute(
            _count,
            operation_name="count_llm_calls_by_request",
            read_only=True,
        )

    async def async_get_max_server_version(self, user_id: int) -> int | None:
        """Return the maximum server_version across LLM calls owned by *user_id*."""
        from peewee import JOIN

        from app.db.models import Request

        def _query() -> int | None:
            return (
                LLMCall.select(peewee.fn.MAX(LLMCall.server_version))
                .join(Request, JOIN.INNER)
                .where(Request.user_id == user_id)
                .scalar()
            )

        return await self._execute(
            _query, operation_name="get_max_server_version_llm_call", read_only=True
        )

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all LLM calls for a user (for sync operations).

        Returns:
            List of LLM call dicts with request_id flattened.
        """
        from peewee import JOIN

        from app.db.models import Request

        def _get() -> list[dict[str, Any]]:
            llm_calls = (
                LLMCall.select(LLMCall, Request)
                .join(Request, JOIN.INNER)
                .where(Request.user_id == user_id)
            )
            result = []
            for call in llm_calls:
                l_dict = model_to_dict(call) or {}
                # Flatten request to just the ID for sync
                if "request" in l_dict and isinstance(l_dict["request"], dict):
                    l_dict["request"] = l_dict["request"]["id"]
                result.append(l_dict)
            return result

        return await self._execute(
            _get, operation_name="get_all_llm_calls_for_user", read_only=True
        )
