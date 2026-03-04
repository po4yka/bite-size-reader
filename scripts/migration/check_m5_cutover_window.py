#!/usr/bin/env python3
"""Check M5 release-window cutover incidents from JSONL events."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from app.migration.cutover_monitor import evaluate_fallback_window


def _parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events-file",
        type=Path,
        default=None,
        help="Path to JSONL events file (defaults to MIGRATION_CUTOVER_EVENTS_FILE or data path).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=None,
        help="Release window size in days (defaults to MIGRATION_RELEASE_WINDOW_DAYS or 14).",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="Override current time (ISO-8601, e.g. 2026-03-04T00:00:00Z).",
    )
    parser.add_argument(
        "--allow-missing-file",
        action="store_true",
        help="Exit 0 if events file does not exist.",
    )
    args = parser.parse_args()

    report = evaluate_fallback_window(
        events_file=args.events_file,
        window_days=args.window_days,
        now=_parse_now(args.now),
    )

    print(f"events_file: {report.events_file}")
    print(f"window_days: {report.window_days}")
    print(f"window_start: {report.window_start.isoformat()}")
    print(f"window_end: {report.window_end.isoformat()}")
    print(f"total_lines: {report.total_line_count}")
    print(f"malformed_lines: {report.malformed_line_count}")

    if not report.events_file_found:
        print("status: missing_events_file")
        return 0 if args.allow_missing_file else 2

    if report.fallback_count > 0:
        print(f"status: cutover_incidents_detected ({report.fallback_count})")
        for surface, count in sorted(report.fallback_by_surface.items()):
            print(f"surface[{surface}]={count}")
        return 1

    print("status: pass_no_cutover_incidents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
