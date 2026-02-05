"""Response formatting components.

This package used to eagerly import many heavy submodules at import time.
Those imports pulled in optional/runtime-specific dependencies and made it
harder to import individual formatters in isolation (e.g. in unit tests).

We keep the same public surface area via lazy attribute loading.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "BatchProgressFormatter": (
        "app.adapters.external.formatting.batch_progress_formatter",
        "BatchProgressFormatter",
    ),
    "DataFormatterImpl": ("app.adapters.external.formatting.data_formatter", "DataFormatterImpl"),
    "DatabasePresenterImpl": (
        "app.adapters.external.formatting.database_presenter",
        "DatabasePresenterImpl",
    ),
    "MessageValidatorImpl": (
        "app.adapters.external.formatting.message_validator",
        "MessageValidatorImpl",
    ),
    "NotificationFormatterImpl": (
        "app.adapters.external.formatting.notification_formatter",
        "NotificationFormatterImpl",
    ),
    "ResponseSenderImpl": (
        "app.adapters.external.formatting.response_sender",
        "ResponseSenderImpl",
    ),
    "SummaryPresenterImpl": (
        "app.adapters.external.formatting.summary_presenter",
        "SummaryPresenterImpl",
    ),
    "TextProcessorImpl": ("app.adapters.external.formatting.text_processor", "TextProcessorImpl"),
    # Protocols
    "DatabasePresenter": ("app.adapters.external.formatting.protocols", "DatabasePresenter"),
    "DataFormatter": ("app.adapters.external.formatting.protocols", "DataFormatter"),
    "MessageValidator": ("app.adapters.external.formatting.protocols", "MessageValidator"),
    "NotificationFormatter": (
        "app.adapters.external.formatting.protocols",
        "NotificationFormatter",
    ),
    "ResponseSender": ("app.adapters.external.formatting.protocols", "ResponseSender"),
    "SummaryPresenter": ("app.adapters.external.formatting.protocols", "SummaryPresenter"),
    "TextProcessor": ("app.adapters.external.formatting.protocols", "TextProcessor"),
}

__all__ = [
    "BatchProgressFormatter",
    "DataFormatter",
    "DataFormatterImpl",
    "DatabasePresenter",
    "DatabasePresenterImpl",
    "MessageValidator",
    "MessageValidatorImpl",
    "NotificationFormatter",
    "NotificationFormatterImpl",
    "ResponseSender",
    "ResponseSenderImpl",
    "SummaryPresenter",
    "SummaryPresenterImpl",
    "TextProcessor",
    "TextProcessorImpl",
]


def __getattr__(name: str) -> Any:  # pragma: no cover
    target = _EXPORTS.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attr_name = target
    module = importlib.import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(list(globals().keys()) + list(_EXPORTS.keys()))
