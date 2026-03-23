"""Persistence and cache helpers for Telegram callback actions."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


class CallbackActionStore:
    """Owns DB-backed lookups and short-lived callback payload caching."""

    def __init__(
        self,
        *,
        asyncio_module: Any = asyncio,
        time_module: Any = time,
        summary_cache_ttl: float = 30.0,
        summary_cache_max: int = 50,
    ) -> None:
        self._asyncio = asyncio_module
        self._time = time_module
        self._summary_cache_ttl = summary_cache_ttl
        self._summary_cache_max = summary_cache_max
        self._summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def get_digest_post(self, channel_id: int, message_id: int) -> Any:
        return await self._asyncio.to_thread(self._load_digest_post_sync, channel_id, message_id)

    @staticmethod
    def _load_digest_post_sync(channel_id: int, message_id: int) -> Any:
        from app.db.models import Channel, ChannelPost

        return (
            ChannelPost.select()
            .join(Channel)
            .where(Channel.id == channel_id, ChannelPost.message_id == message_id)
            .first()
        )

    async def toggle_save(self, summary_id: str) -> bool | None:
        new_state = await self._asyncio.to_thread(self._toggle_save_sync, summary_id)
        self._summary_cache.pop(summary_id, None)
        return new_state

    @staticmethod
    def _toggle_save_sync(summary_id: str) -> bool | None:
        from app.db.models import Summary

        if summary_id.startswith("req:"):
            request_id = int(summary_id[4:])
            summary = Summary.get_or_none(Summary.request_id == request_id)
        else:
            summary = Summary.get_or_none(Summary.id == int(summary_id))
        if not summary:
            return None
        summary.is_favorited = not summary.is_favorited
        summary.save()
        return summary.is_favorited

    async def lookup_retry_url(self, correlation_id: str) -> str | None:
        return await self._asyncio.to_thread(self._lookup_retry_url_sync, correlation_id)

    @staticmethod
    def _lookup_retry_url_sync(correlation_id: str) -> str | None:
        from app.db.models import Request

        request = (
            Request.select(Request.input_url)
            .where(Request.correlation_id == correlation_id)
            .order_by(Request.created_at.desc())
            .first()
        )
        return request.input_url if request else None

    async def load_summary_payload(
        self,
        summary_id: str,
        *,
        correlation_id: str | None = None,
        cache: dict[str, tuple[float, dict[str, Any]]] | None = None,
        loader: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any] | None:
        """Load summary JSON payload from database with short-lived caching."""
        active_cache = self._summary_cache if cache is None else cache
        active_loader = self._load_summary_payload_sync if loader is None else loader

        now = self._time.time()
        cached = active_cache.get(summary_id)
        if cached is not None:
            cached_at, cached_payload = cached
            if now - cached_at < self._summary_cache_ttl:
                return cached_payload

        try:
            result = await self._asyncio.to_thread(active_loader, summary_id)
            if result is not None:
                if len(active_cache) >= self._summary_cache_max:
                    oldest_key = min(active_cache, key=lambda key: active_cache[key][0])
                    active_cache.pop(oldest_key, None)
                active_cache[summary_id] = (now, result)
            return result
        except Exception as exc:
            logger.exception(
                "load_summary_payload_failed",
                extra={"summary_id": summary_id, "error": str(exc), "cid": correlation_id},
            )
            return None

    @staticmethod
    def _load_summary_payload_sync(summary_id: str) -> dict[str, Any] | None:
        from app.db.models import Request, Summary

        if summary_id.startswith("req:"):
            request_id = int(summary_id[4:])
            summary = Summary.get_or_none(Summary.request_id == request_id)
        else:
            summary = Summary.get_or_none(Summary.id == int(summary_id))

        if not summary:
            return None

        request = Request.get_or_none(Request.id == summary.request_id)
        url = request.normalized_url if request else None

        payload = summary.json_payload or {}
        if not isinstance(payload, dict):
            payload = {}

        return {
            "id": str(summary.id),
            "request_id": summary.request_id,
            "url": url,
            "lang": summary.lang,
            "insights": summary.insights_json if isinstance(summary.insights_json, dict) else None,
            **payload,
        }
