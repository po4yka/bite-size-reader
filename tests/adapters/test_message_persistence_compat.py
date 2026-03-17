"""Tests for message_persistence backward-compat shim."""

from __future__ import annotations

import pytest


def test_message_persistence_compat_shim_imports() -> None:
    from app.adapters.telegram.message_persistence import MessagePersistence
    from app.infrastructure.persistence.message_persistence import (
        MessagePersistence as Canonical,
    )

    assert MessagePersistence is Canonical


def test_message_persistence_compat_shim_raises_for_unknown() -> None:
    import app.adapters.telegram.message_persistence as shim

    with pytest.raises(AttributeError, match="has no attribute 'NonExistent'"):
        _ = shim.NonExistent  # type: ignore[attr-defined]
