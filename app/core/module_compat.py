"""Helpers for compatibility modules that lazy-load legacy exports."""

from __future__ import annotations

import importlib
from typing import Any


def load_compat_symbol(
    *,
    module_name: str,
    attribute_name: str,
    export_map: dict[str, tuple[str, str]],
    namespace: dict[str, Any],
) -> Any:
    """Resolve and memoize a compatibility symbol from an export map."""
    target = export_map.get(attribute_name)
    if target is None:
        msg = f"module {module_name!r} has no attribute {attribute_name!r}"
        raise AttributeError(msg)
    target_module, symbol = target
    module = importlib.import_module(target_module)
    value = getattr(module, symbol)
    namespace[attribute_name] = value
    return value
