"""Helper utilities for working with user interaction persistence."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import log_exception

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.persistence.sqlite.repositories.user_repository import (
        SqliteUserRepositoryAdapter,
    )

logger = logging.getLogger(__name__)


_update_tasks: set[asyncio.Task] = set()


def safe_update_user_interaction(
    db: DatabaseSessionManager | Any,
    *,
    interaction_id: int | None,
    logger_: logging.Logger | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    updates: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Sync helper for updating user interaction (legacy, prefer async version)."""
    # This helper is legacy and should be avoided in async code
    prepared = _prepare_interaction_update(
        interaction_id,
        updates=updates,
        start_time=start_time,
        end_time=end_time,
        fields=fields,
    )

    if prepared is None:
        return

    payload, update_mapping = prepared

    try:
        if hasattr(db, "update_user_interaction"):
            db.update_user_interaction(
                interaction_id,
                updates=update_mapping,
                **payload,
            )
            return

        if hasattr(db, "async_update_user_interaction"):
            coro = db.async_update_user_interaction(
                interaction_id=interaction_id,
                updates=update_mapping,
                **payload,
            )
        else:
            from app.infrastructure.persistence.sqlite.repositories.user_repository import (
                SqliteUserRepositoryAdapter,
            )

            user_repo = SqliteUserRepositoryAdapter(db)
            coro = user_repo.async_update_user_interaction(
                interaction_id=interaction_id,
                updates=update_mapping,
                **payload,
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
        else:
            task = loop.create_task(coro)
            _update_tasks.add(task)

            def _on_task_done(t: asyncio.Task) -> None:
                _update_tasks.discard(t)
                if t.cancelled():
                    return
                exc = t.exception()
                if exc:
                    log = logger_ if logger_ is not None else logger
                    log_exception(
                        log,
                        "user_interaction_update_task_failed",
                        exc,
                        level="warning",
                        interaction_id=interaction_id,
                    )

            task.add_done_callback(_on_task_done)
    except Exception as exc:
        log = logger_ if logger_ is not None else logger
        log.warning(
            "user_interaction_update_failed",
            extra={"interaction_id": interaction_id, "error": str(exc)},
        )


async def async_safe_update_user_interaction(
    user_repo: SqliteUserRepositoryAdapter | Any,
    *,
    interaction_id: int | None,
    logger_: logging.Logger | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    updates: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Async counterpart to :func:`safe_update_user_interaction`."""
    prepared = _prepare_interaction_update(
        interaction_id,
        updates=updates,
        start_time=start_time,
        end_time=end_time,
        fields=fields,
    )

    if prepared is None:
        return

    payload, update_mapping = prepared

    try:
        await user_repo.async_update_user_interaction(
            interaction_id=interaction_id,
            updates=update_mapping,
            **payload,
        )
    except Exception as exc:
        log = logger_ if logger_ is not None else logger
        log.warning(
            "user_interaction_update_failed",
            extra={"interaction_id": interaction_id, "error": str(exc)},
        )


def _prepare_interaction_update(
    interaction_id: int | None,
    *,
    updates: dict[str, Any] | None,
    start_time: float | None,
    end_time: float | None,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
    """Normalize arguments shared between sync and async helpers."""
    if interaction_id is None or interaction_id <= 0:
        return None

    if updates is not None and fields:
        msg = "Cannot mix 'updates' with individual field arguments"
        raise ValueError(msg)

    payload = dict(fields)

    if start_time is not None and "processing_time_ms" not in payload and updates is None:
        stop_time = end_time if end_time is not None else time.time()
        duration_ms = max(0, int((stop_time - start_time) * 1000))
        payload["processing_time_ms"] = duration_ms

    return payload, updates
