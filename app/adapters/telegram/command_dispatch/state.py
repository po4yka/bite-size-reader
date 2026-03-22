"""Mutable runtime collaborators used by command handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TelegramCommandRuntimeState:
    url_processor: Any
    url_handler: Any | None = None
    topic_searcher: Any | None = None
    local_searcher: Any | None = None
    _task_manager: Any | None = None
    hybrid_search: Any | None = None
