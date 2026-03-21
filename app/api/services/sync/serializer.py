"""Serialization helpers for sync envelopes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.api.models.responses import SyncEntityEnvelope
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

logger = get_logger(__name__)


class SyncEnvelopeSerializer:
    def _deleted_at(self, record: dict[str, Any]) -> str | None:
        raw = record.get("deleted_at")
        return self._coerce_iso(raw) if raw else None

    @staticmethod
    def _resolve_request_id(record: dict[str, Any]) -> int | None:
        request_val = record.get("request")
        if isinstance(request_val, int):
            return request_val
        if isinstance(request_val, dict):
            return request_val.get("id")
        return None

    def _coerce_iso(self, dt_value: Any) -> str:
        if hasattr(dt_value, "isoformat") and not isinstance(dt_value, str):
            return dt_value.isoformat() + "Z"
        if isinstance(dt_value, str):
            try:
                return datetime.fromisoformat(dt_value.replace("Z", "+00:00")).isoformat() + "Z"
            except Exception:
                logger.warning("datetime_parse_failed", exc_info=True)
                return datetime.now(UTC).isoformat() + "Z"
        return datetime.now(UTC).isoformat() + "Z"

    def serialize_request(self, request: dict[str, Any]) -> SyncEntityEnvelope:
        payload = None
        if not request.get("is_deleted"):
            payload = {
                "id": request.get("id"),
                "type": request.get("type"),
                "status": request.get("status"),
                "input_url": request.get("input_url"),
                "normalized_url": request.get("normalized_url"),
                "correlation_id": request.get("correlation_id"),
                "created_at": self._coerce_iso(request.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="request",
            id=request.get("id"),
            server_version=int(request.get("server_version") or 0),
            updated_at=self._coerce_iso(request.get("updated_at")),
            deleted_at=self._deleted_at(request),
            request=payload,
        )

    def serialize_summary(self, summary: dict[str, Any]) -> SyncEntityEnvelope:
        payload = None
        if not summary.get("is_deleted"):
            payload = {
                "id": summary.get("id"),
                "request_id": self._resolve_request_id(summary),
                "lang": summary.get("lang"),
                "is_read": summary.get("is_read"),
                "json_payload": summary.get("json_payload"),
                "created_at": self._coerce_iso(summary.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="summary",
            id=summary.get("id"),
            server_version=int(summary.get("server_version") or 0),
            updated_at=self._coerce_iso(summary.get("updated_at")),
            deleted_at=self._deleted_at(summary),
            summary=payload,
        )

    def serialize_crawl_result(self, crawl: dict[str, Any]) -> SyncEntityEnvelope:
        payload = None
        if not crawl.get("is_deleted"):
            payload = {
                "request_id": self._resolve_request_id(crawl),
                "source_url": crawl.get("source_url"),
                "endpoint": crawl.get("endpoint"),
                "http_status": crawl.get("http_status"),
                "metadata": crawl.get("metadata_json"),
                "latency_ms": crawl.get("latency_ms"),
            }
        return SyncEntityEnvelope(
            entity_type="crawl_result",
            id=crawl.get("id"),
            server_version=int(crawl.get("server_version") or 0),
            updated_at=self._coerce_iso(crawl.get("updated_at")),
            deleted_at=self._deleted_at(crawl),
            crawl_result=payload,
        )

    def serialize_llm_call(self, call: dict[str, Any]) -> SyncEntityEnvelope:
        payload = None
        if not call.get("is_deleted"):
            payload = {
                "request_id": self._resolve_request_id(call),
                "provider": call.get("provider"),
                "model": call.get("model"),
                "status": call.get("status"),
                "tokens_prompt": call.get("tokens_prompt"),
                "tokens_completion": call.get("tokens_completion"),
                "cost_usd": call.get("cost_usd"),
                "created_at": self._coerce_iso(call.get("created_at")),
            }
        return SyncEntityEnvelope(
            entity_type="llm_call",
            id=call.get("id"),
            server_version=int(call.get("server_version") or 0),
            updated_at=self._coerce_iso(call.get("updated_at")),
            deleted_at=self._deleted_at(call),
            llm_call=payload,
        )

    def serialize_highlight(self, highlight: dict[str, Any]) -> SyncEntityEnvelope:
        summary_val = highlight.get("summary")
        summary_id = summary_val.get("id") if isinstance(summary_val, dict) else summary_val
        payload = {
            "id": str(highlight.get("id")),
            "summary_id": str(summary_id) if summary_id is not None else None,
            "text": highlight.get("text"),
            "start_offset": highlight.get("start_offset"),
            "end_offset": highlight.get("end_offset"),
            "color": highlight.get("color"),
            "note": highlight.get("note"),
            "created_at": self._coerce_iso(highlight.get("created_at")),
            "updated_at": self._coerce_iso(highlight.get("updated_at")),
        }
        return SyncEntityEnvelope(
            entity_type="highlight",
            id=str(highlight.get("id")),
            server_version=int(highlight.get("server_version") or 0),
            updated_at=self._coerce_iso(highlight.get("updated_at")),
            highlight=payload,
        )

    def serialize_user(self, user: dict[str, Any]) -> SyncEntityEnvelope:
        updated_at = user.get("updated_at")
        created_at = user.get("created_at")
        return SyncEntityEnvelope(
            entity_type="user",
            id=user.get("telegram_user_id"),
            server_version=int(user.get("server_version") or 0),
            updated_at=self._coerce_iso(updated_at),
            preference={
                "username": user.get("username"),
                "is_owner": user.get("is_owner"),
                "preferences": user.get("preferences_json"),
                "created_at": self._coerce_iso(created_at),
            },
        )

    def serialize_tag(self, tag: dict[str, Any]) -> SyncEntityEnvelope:
        payload = None
        if not tag.get("is_deleted"):
            payload = {
                "id": tag.get("id"),
                "name": tag.get("name"),
                "normalized_name": tag.get("normalized_name"),
                "color": tag.get("color"),
                "server_version": int(tag.get("server_version") or 0),
                "is_deleted": tag.get("is_deleted", False),
                "created_at": self._coerce_iso(tag.get("created_at")),
                "updated_at": self._coerce_iso(tag.get("updated_at")),
            }
        return SyncEntityEnvelope(
            entity_type="tag",
            id=tag.get("id"),
            server_version=int(tag.get("server_version") or 0),
            updated_at=self._coerce_iso(tag.get("updated_at")),
            deleted_at=self._deleted_at(tag),
            tag=payload,
        )

    def serialize_summary_tag(self, st: dict[str, Any]) -> SyncEntityEnvelope:
        summary_val = st.get("summary")
        summary_id = summary_val.get("id") if isinstance(summary_val, dict) else summary_val
        tag_val = st.get("tag")
        tag_id = tag_val.get("id") if isinstance(tag_val, dict) else tag_val
        payload = {
            "id": st.get("id"),
            "summary_id": summary_id,
            "tag_id": tag_id,
            "source": st.get("source"),
            "server_version": int(st.get("server_version") or 0),
            "created_at": self._coerce_iso(st.get("created_at")),
        }
        return SyncEntityEnvelope(
            entity_type="summary_tag",
            id=st.get("id"),
            server_version=int(st.get("server_version") or 0),
            updated_at=self._coerce_iso(st.get("created_at")),
            summary_tag=payload,
        )
