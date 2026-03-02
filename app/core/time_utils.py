from __future__ import annotations

from datetime import datetime, timezone

try:  # Python 3.11+
    from datetime import UTC
except ImportError:  # pragma: no cover - Python < 3.11
    UTC = timezone.utc  # noqa: UP017


def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def format_iso_z(value: datetime) -> str:
    """Format a datetime as UTC ISO8601 with a trailing Z suffix."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
