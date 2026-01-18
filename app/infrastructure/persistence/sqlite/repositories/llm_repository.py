"""SQLite implementation of LLM repository.

This adapter handles logging and retrieval of LLM call data.
"""

from __future__ import annotations

from typing import Any

from app.db.models import LLMCall, model_to_dict
from app.db.utils import prepare_json_payload
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


class SqliteLLMRepositoryAdapter(SqliteBaseRepository):
    """Adapter for LLM call logging operations."""

    async def async_insert_llm_call(self, **kwargs: Any) -> int:
        """Insert an LLM call log record."""

        def _insert() -> int:
            provider = kwargs.get("provider")
            response_text = kwargs.get("response_text")

            # Prepare payloads using shared utilities
            headers_payload = prepare_json_payload(kwargs.get("request_headers_json"), default={})
            messages_payload = prepare_json_payload(kwargs.get("request_messages_json"), default=[])
            response_payload = prepare_json_payload(kwargs.get("response_json"), default={})
            error_context_payload = prepare_json_payload(kwargs.get("error_context_json"))

            payload = {
                "request": kwargs.get("request_id"),
                "provider": provider,
                "model": kwargs.get("model"),
                "endpoint": kwargs.get("endpoint"),
                "request_headers_json": headers_payload,
                "request_messages_json": messages_payload,
                "tokens_prompt": kwargs.get("tokens_prompt"),
                "tokens_completion": kwargs.get("tokens_completion"),
                "cost_usd": kwargs.get("cost_usd"),
                "latency_ms": kwargs.get("latency_ms"),
                "status": kwargs.get("status"),
                "error_text": kwargs.get("error_text"),
                "structured_output_used": kwargs.get("structured_output_used"),
                "structured_output_mode": kwargs.get("structured_output_mode"),
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

            call = LLMCall.create(**payload)
            return call.id

        return await self._execute(_insert, operation_name="insert_llm_call")

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
