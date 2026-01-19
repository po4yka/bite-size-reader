"""Database utilities and helpers.

This module re-exports utilities from json_utils for backward compatibility.
New code should import directly from app.db.json_utils.
"""

from __future__ import annotations

# Re-export from json_utils for backward compatibility
from app.db.json_utils import (
    normalize_json_container,
    prepare_json_payload,
)

__all__ = [
    "normalize_json_container",
    "prepare_json_payload",
]
