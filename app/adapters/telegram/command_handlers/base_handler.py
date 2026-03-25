"""Shared dependency wiring for Telegram command handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.adapters.external.formatting.protocols import (
        ResponseFormatterFacade as ResponseFormatter,
    )
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager


class HandlerDependenciesMixin:
    """Provide common cfg/db/formatter initialization for handlers."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._formatter = response_formatter
