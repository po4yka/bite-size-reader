"""Adapters for external systems (Telegram, Firecrawl, OpenRouter, etc.).

Keep package imports lightweight: heavy submodules are exposed via lazy
attribute loading to avoid importing optional dependencies unless needed.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["telegram_bot"]


def __getattr__(name: str) -> Any:  # pragma: no cover
    if name != "telegram_bot":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module = importlib.import_module("app.adapters.telegram.telegram_bot")
    globals()[name] = module
    return module


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(list(globals().keys()) + __all__)
