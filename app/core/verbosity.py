"""Per-user verbosity levels for notification formatting.

Supports two modes:
- READER (default): consolidated single progress message, edited in-place
- DEBUG: full technical details with multiple messages (legacy behaviour)
"""

from __future__ import annotations

import enum
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 300  # 5 minutes


class VerbosityLevel(enum.Enum):
    """User-facing verbosity modes."""

    READER = "reader"
    DEBUG = "debug"


class VerbosityResolver:
    """Resolves per-user verbosity from ``User.preferences_json``."""

    def __init__(self, user_repo: SqliteUserRepositoryAdapter) -> None:
        self._user_repo = user_repo
        # uid -> (level, timestamp)
        self._cache: dict[int, tuple[VerbosityLevel, float]] = {}

    async def get_verbosity(self, message: Any) -> VerbosityLevel:
        """Return the verbosity level for the user who sent *message*."""
        uid = self._extract_uid(message)
        if uid is None:
            return VerbosityLevel.READER

        # Check cache
        cached = self._cache.get(uid)
        if cached is not None:
            level, ts = cached
            if time.monotonic() - ts < _CACHE_TTL_SEC:
                return level

        # Read from DB
        try:
            user = await self._user_repo.async_get_user_by_telegram_id(uid)
            prefs = (user or {}).get("preferences_json") or {}
            raw = prefs.get("verbosity", "reader") if isinstance(prefs, dict) else "reader"
            level = VerbosityLevel(raw) if raw in ("reader", "debug") else VerbosityLevel.READER
        except Exception:
            logger.debug("verbosity_resolve_fallback", extra={"uid": uid})
            level = VerbosityLevel.READER

        self._cache[uid] = (level, time.monotonic())
        return level

    def invalidate_cache(self, uid: int) -> None:
        """Remove a cached entry so the next lookup hits the DB."""
        self._cache.pop(uid, None)

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_uid(message: Any) -> int | None:
        from_user = getattr(message, "from_user", None)
        return getattr(from_user, "id", None) if from_user is not None else None
