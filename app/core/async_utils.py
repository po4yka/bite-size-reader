"""Async helper utilities."""

from __future__ import annotations

import asyncio


def raise_if_cancelled(exc: BaseException) -> None:
    """Re-raise ``asyncio.CancelledError`` instances to preserve cancellation semantics."""

    if isinstance(exc, asyncio.CancelledError):  # pragma: no cover - simple guard
        raise exc
