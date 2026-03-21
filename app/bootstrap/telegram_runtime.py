"""Edge wiring helpers for Telegram bot startup."""

from __future__ import annotations

from typing import Any

from app.di.repositories import build_audit_log_repository
from app.di.telegram import build_telegram_runtime


def build_bot_runtime(
    *,
    cfg: Any,
    db: Any,
    safe_reply_func: Any,
    reply_json_func: Any,
    db_write_queue: Any = None,
    audit_task_registry: set[Any] | None = None,
) -> Any:
    return build_telegram_runtime(
        cfg=cfg,
        db=db,
        safe_reply_func=safe_reply_func,
        reply_json_func=reply_json_func,
        db_write_queue=db_write_queue,
        audit_task_registry=audit_task_registry,
    )


def create_bot_audit_repository(db: Any) -> Any:
    return build_audit_log_repository(db)
