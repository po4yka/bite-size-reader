"""Error collection helpers for sync results."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.karakeep.models import SyncResult


def record_error(result: SyncResult, message: str, retryable: bool) -> None:
    if message not in result.errors:
        result.errors.append(message)
    if retryable:
        result.retryable_errors.append(message)
    else:
        result.permanent_errors.append(message)
