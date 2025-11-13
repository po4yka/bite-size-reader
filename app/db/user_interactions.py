"""Helper utilities for working with user interaction persistence."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import Database

logger = logging.getLogger(__name__)


def safe_update_user_interaction(
    db: Database,
    *,
    interaction_id: int | None,
    logger_: logging.Logger | None = None,
    start_time: float | None = None,
    end_time: float | None = None,
    updates: dict[str, Any] | None = None,
    **fields: Any,
) -> None:
    """Safely update an interaction record.

    This helper wraps :meth:`Database.update_user_interaction`, ensuring that
    ``interaction_id`` is valid before attempting to persist the update and
    capturing any exceptions as warnings.  When ``start_time`` is provided and
    ``processing_time_ms`` is omitted, the helper automatically calculates the
    latency using either ``end_time`` or the current time.

    Parameters
    ----------
    db:
        The database instance used to persist the interaction update.
    interaction_id:
        The primary key of the interaction to update. If ``None`` or ``<= 0``
        the call is ignored.
    logger_:
        Optional logger used for warning output. Falls back to this module's
        logger when omitted.
    start_time:
        Optional start timestamp (in seconds). When provided and
        ``processing_time_ms`` is not explicitly set, the helper computes the
        latency automatically.
    end_time:
        Optional end timestamp. Defaults to ``time.time()`` when ``start_time``
        is provided without an explicit end time.
    updates:
        Optional mapping passed straight through to
        :meth:`Database.update_user_interaction`.
    **fields:
        Individual field overrides that mirror the database method signature.

    """
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
        db.update_user_interaction(
            interaction_id=interaction_id,
            updates=update_mapping,
            **payload,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort logging
        log = logger_ if logger_ is not None else logger
        log.warning(
            "user_interaction_update_failed",
            extra={"interaction_id": interaction_id, "error": str(exc)},
        )


async def async_safe_update_user_interaction(
    db: Database,
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
        await db.async_update_user_interaction(
            interaction_id=interaction_id,
            updates=update_mapping,
            **payload,
        )
    except Exception as exc:  # noqa: BLE001 - best-effort logging
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
