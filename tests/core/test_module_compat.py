"""Tests for app.core.module_compat."""

from __future__ import annotations

import pytest

from app.core.module_compat import load_compat_symbol


def test_load_compat_symbol_resolves_known_attribute() -> None:
    export_map = {"UTC": ("app.core.time_utils", "UTC")}
    namespace: dict = {}
    val = load_compat_symbol(
        module_name="test_module",
        attribute_name="UTC",
        export_map=export_map,
        namespace=namespace,
    )
    from app.core.time_utils import UTC

    assert val is UTC
    assert namespace["UTC"] is UTC


def test_load_compat_symbol_memoizes_into_namespace() -> None:
    export_map = {"UTC": ("app.core.time_utils", "UTC")}
    namespace: dict = {}
    load_compat_symbol(
        module_name="test_module",
        attribute_name="UTC",
        export_map=export_map,
        namespace=namespace,
    )
    assert "UTC" in namespace


def test_load_compat_symbol_raises_for_unknown_attribute() -> None:
    export_map = {"known": ("app.core.time_utils", "UTC")}
    with pytest.raises(AttributeError, match="has no attribute 'unknown'"):
        load_compat_symbol(
            module_name="my_compat_module",
            attribute_name="unknown",
            export_map=export_map,
            namespace={},
        )
