"""Redis cache for batch processing progress with Pub/Sub support.

Enables real-time progress updates during batch URL processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.config import AppConfig
    from app.infrastructure.cache.redis_cache import RedisCache

logger = logging.getLogger(__name__)


class BatchProgressCache:
    """Store and broadcast batch processing progress via Redis.

    Key patterns:
    - Progress state: bsr:batch:progress:{session_id}
      Value: {"status": str, "processed": int, "total": int, "percent": float, ...}
      TTL: 1 hour (configurable via REDIS_BATCH_PROGRESS_TTL_SECONDS)

    - Pub/Sub channel: bsr:batch:updates:{session_id}
      Messages: {"event": str, "data": {...}, "timestamp": str}

    Fallback: On Redis unavailable, callers should use DB polling.
    """

    def __init__(self, cache: RedisCache, cfg: AppConfig) -> None:
        self._cache = cache
        self._cfg = cfg

    @property
    def enabled(self) -> bool:
        return self._cache.enabled

    def _progress_key(self, session_id: int | str) -> str:
        """Build the progress state key."""
        from app.infrastructure.redis import redis_key

        return redis_key(self._cfg.redis.prefix, "batch", "progress", str(session_id))

    def _channel_name(self, session_id: int | str) -> str:
        """Build the Pub/Sub channel name."""
        return f"{self._cfg.redis.prefix}:batch:updates:{session_id}"

    async def get_progress(self, session_id: int | str) -> dict[str, Any] | None:
        """Get current batch progress from cache.

        Args:
            session_id: Batch session ID.

        Returns:
            Progress dict or None if not cached.
        """
        if not self._cache.enabled:
            return None

        cached = await self._cache.get_json("batch", "progress", str(session_id))
        if isinstance(cached, dict):
            logger.debug(
                "batch_progress_cache_hit",
                extra={"session_id": session_id},
            )
            return cached
        return None

    async def set_progress(
        self,
        session_id: int | str,
        *,
        status: str,
        processed: int,
        total: int,
        percent: float | None = None,
        successful_count: int = 0,
        failed_count: int = 0,
        current_url: str | None = None,
        error_message: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """Set batch progress in cache.

        Args:
            session_id: Batch session ID.
            status: Current status (processing, completed, error).
            processed: Number of URLs processed so far.
            total: Total number of URLs.
            percent: Progress percentage (computed if not provided).
            successful_count: Number of successfully processed URLs.
            failed_count: Number of failed URLs.
            current_url: URL currently being processed.
            error_message: Error message if status is "error".
            extra: Additional metadata to include.

        Returns:
            True if cached successfully, False otherwise.
        """
        if not self._cache.enabled:
            return False

        # Compute percent if not provided
        if percent is None:
            percent = (processed / total * 100) if total > 0 else 0.0

        value: dict[str, Any] = {
            "session_id": int(session_id) if isinstance(session_id, str) else session_id,
            "status": status,
            "processed": processed,
            "total": total,
            "percent": round(percent, 1),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }

        if current_url:
            value["current_url"] = current_url
        if error_message:
            value["error_message"] = error_message
        if extra:
            value.update(extra)

        ttl = self._cfg.redis.batch_progress_ttl_seconds
        success = await self._cache.set_json(
            value=value,
            ttl_seconds=ttl,
            parts=("batch", "progress", str(session_id)),
        )

        if success:
            logger.debug(
                "batch_progress_cached",
                extra={
                    "session_id": session_id,
                    "status": status,
                    "percent": percent,
                },
            )
        return success

    async def publish_update(
        self,
        session_id: int | str,
        event: str,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Publish a progress update to the Pub/Sub channel.

        Args:
            session_id: Batch session ID.
            event: Event type (progress, completed, error, item_completed, etc.).
            data: Event data payload.

        Returns:
            True if published successfully, False otherwise.
        """
        if not self._cache.enabled:
            return False

        client = await self._cache._get_client()
        if not client:
            return False

        channel = self._channel_name(session_id)
        message = {
            "event": event,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        try:
            await client.publish(channel, json.dumps(message))
            logger.debug(
                "batch_update_published",
                extra={"session_id": session_id, "event": event, "channel": channel},
            )
            return True
        except Exception as exc:
            logger.warning(
                "batch_update_publish_failed",
                exc_info=True,
                extra={"session_id": session_id, "event": event, "error": str(exc)},
            )
            return False

    async def subscribe_updates(
        self, session_id: int | str
    ) -> AsyncIterator[dict[str, Any]] | None:
        """Subscribe to progress updates for a batch session.

        Yields:
            Progress update messages as they arrive.

        Returns:
            None if Redis is unavailable.
        """
        if not self._cache.enabled:
            return None

        client = await self._cache._get_client()
        if not client:
            return None

        channel = self._channel_name(session_id)

        async def _updates() -> AsyncIterator[dict[str, Any]]:
            pubsub = client.pubsub()
            await pubsub.subscribe(channel)
            try:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            yield data
                        except json.JSONDecodeError:
                            continue
            finally:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()

        return _updates()

    async def update_and_publish(
        self,
        session_id: int | str,
        *,
        status: str,
        processed: int,
        total: int,
        successful_count: int = 0,
        failed_count: int = 0,
        current_url: str | None = None,
        error_message: str | None = None,
        extra: dict[str, Any] | None = None,
        event: str = "progress",
    ) -> bool:
        """Update progress state and publish update in one call.

        This is a convenience method that combines set_progress() and publish_update().

        Returns:
            True if both operations succeeded, False otherwise.
        """
        percent = (processed / total * 100) if total > 0 else 0.0

        # Update state
        state_ok = await self.set_progress(
            session_id,
            status=status,
            processed=processed,
            total=total,
            percent=percent,
            successful_count=successful_count,
            failed_count=failed_count,
            current_url=current_url,
            error_message=error_message,
            extra=extra,
        )

        # Publish update
        pub_data: dict[str, Any] = {
            "status": status,
            "processed": processed,
            "total": total,
            "percent": round(percent, 1),
            "successful_count": successful_count,
            "failed_count": failed_count,
        }
        if current_url:
            pub_data["current_url"] = current_url
        if error_message:
            pub_data["error_message"] = error_message

        pub_ok = await self.publish_update(session_id, event, pub_data)

        return state_ok and pub_ok

    async def delete_progress(self, session_id: int | str) -> bool:
        """Delete batch progress from cache.

        Called when batch processing is complete and progress is no longer needed.

        Returns:
            True if deleted, False otherwise.
        """
        if not self._cache.enabled:
            return False

        client = await self._cache._get_client()
        if not client:
            return False

        key = self._progress_key(session_id)
        try:
            await client.delete(key)
            logger.debug(
                "batch_progress_deleted",
                extra={"session_id": session_id},
            )
            return True
        except Exception as exc:
            logger.warning(
                "batch_progress_delete_failed",
                exc_info=True,
                extra={"session_id": session_id, "error": str(exc)},
            )
            return False
