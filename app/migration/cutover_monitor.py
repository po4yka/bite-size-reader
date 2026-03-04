from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EVENTS_FILE_ENV = "MIGRATION_CUTOVER_EVENTS_FILE"
_WINDOW_DAYS_ENV = "MIGRATION_RELEASE_WINDOW_DAYS"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _default_events_file() -> Path:
    raw = os.getenv(_EVENTS_FILE_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("data/migration_cutover_events.jsonl")


def _configured_events_file() -> Path | None:
    raw = os.getenv(_EVENTS_FILE_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _default_window_days() -> int:
    raw = os.getenv(_WINDOW_DAYS_ENV, "14").strip()
    try:
        parsed = int(raw)
    except ValueError:
        return 14
    if parsed < 1:
        return 1
    if parsed > 365:
        return 365
    return parsed


def record_cutover_event(
    *,
    event_type: str,
    surface: str,
    reason: str | None = None,
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    event_payload: dict[str, Any] = {
        "ts": _utc_now().isoformat(),
        "event_type": event_type,
        "surface": surface,
    }
    if reason:
        event_payload["reason"] = reason
    if correlation_id:
        event_payload["correlation_id"] = correlation_id
    if metadata:
        event_payload["metadata"] = metadata

    logger.info("m5_cutover_event", extra=event_payload)

    path = _configured_events_file()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event_payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning(
            "m5_cutover_event_write_failed",
            extra={"path": str(path), "error": str(exc)},
        )


@dataclass(frozen=True)
class CutoverWindowReport:
    events_file: Path
    events_file_found: bool
    window_days: int
    window_start: datetime
    window_end: datetime
    fallback_count: int
    fallback_by_surface: dict[str, int]
    malformed_line_count: int
    total_line_count: int


def evaluate_fallback_window(
    *,
    events_file: Path | None = None,
    window_days: int | None = None,
    now: datetime | None = None,
) -> CutoverWindowReport:
    path = (events_file or _default_events_file()).expanduser()
    days = window_days if isinstance(window_days, int) else _default_window_days()
    days = max(1, min(365, days))
    end = (now or _utc_now()).astimezone(UTC)
    start = end - timedelta(days=days)

    if not path.is_file():
        return CutoverWindowReport(
            events_file=path,
            events_file_found=False,
            window_days=days,
            window_start=start,
            window_end=end,
            fallback_count=0,
            fallback_by_surface={},
            malformed_line_count=0,
            total_line_count=0,
        )

    fallback_count = 0
    fallback_by_surface: dict[str, int] = {}
    malformed = 0
    total_lines = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            total_lines += 1
            raw = line.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if not isinstance(parsed, dict):
                malformed += 1
                continue

            ts_raw = parsed.get("ts")
            event_time = _parse_timestamp(str(ts_raw) if ts_raw is not None else "")
            if event_time is None or event_time < start or event_time > end:
                continue

            if str(parsed.get("event_type") or "") != "python_fallback":
                continue

            fallback_count += 1
            surface = str(parsed.get("surface") or "unknown")
            fallback_by_surface[surface] = fallback_by_surface.get(surface, 0) + 1

    return CutoverWindowReport(
        events_file=path,
        events_file_found=True,
        window_days=days,
        window_start=start,
        window_end=end,
        fallback_count=fallback_count,
        fallback_by_surface=fallback_by_surface,
        malformed_line_count=malformed,
        total_line_count=total_lines,
    )
