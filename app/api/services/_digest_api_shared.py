"""Shared helpers for digest API services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.exceptions import FeatureDisabledError
from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    import asyncio

    from app.config.digest import ChannelDigestConfig

logger = get_logger("app.api.services.digest_api_service")
_background_digest_tasks: set[asyncio.Task[None]] = set()


def require_enabled(cfg: ChannelDigestConfig) -> None:
    """Raise when digest functionality is disabled."""
    if not cfg.enabled:
        raise FeatureDisabledError("digest", "Channel digest is not enabled.")


def track_background_task(task: asyncio.Task[None]) -> None:
    """Keep a strong reference for fire-and-forget tasks until completion."""
    _background_digest_tasks.add(task)

    def _on_done(done_task: asyncio.Task[None]) -> None:
        _background_digest_tasks.discard(done_task)

    task.add_done_callback(_on_done)
