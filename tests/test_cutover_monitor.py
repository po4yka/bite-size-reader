from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.migration.cutover_monitor import evaluate_fallback_window, record_cutover_event

if TYPE_CHECKING:
    from pathlib import Path


def test_record_cutover_event_writes_jsonl(tmp_path: Path, monkeypatch) -> None:
    events_file = tmp_path / "cutover_events.jsonl"
    monkeypatch.setenv("MIGRATION_CUTOVER_EVENTS_FILE", str(events_file))

    record_cutover_event(
        event_type="python_fallback",
        surface="summary_contract",
        reason="test_reason",
        correlation_id="cid-1",
        metadata={"backend": "rust"},
    )

    lines = events_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event_type"] == "python_fallback"
    assert payload["surface"] == "summary_contract"
    assert payload["reason"] == "test_reason"
    assert payload["correlation_id"] == "cid-1"
    assert payload["metadata"]["backend"] == "rust"


def test_evaluate_fallback_window_counts_recent_events(tmp_path: Path) -> None:
    now = datetime(2026, 3, 4, 12, 0, tzinfo=UTC)
    events_file = tmp_path / "events.jsonl"

    rows = [
        {
            "ts": (now - timedelta(days=1)).isoformat(),
            "event_type": "python_fallback",
            "surface": "summary_contract",
        },
        {
            "ts": (now - timedelta(days=20)).isoformat(),
            "event_type": "python_fallback",
            "surface": "interface_mobile_route",
        },
        {
            "ts": (now - timedelta(hours=3)).isoformat(),
            "event_type": "rust_primary",
            "surface": "summary_contract",
        },
    ]
    with events_file.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
        handle.write("not-json\n")

    report = evaluate_fallback_window(events_file=events_file, window_days=14, now=now)

    assert report.events_file_found is True
    assert report.fallback_count == 1
    assert report.fallback_by_surface == {"summary_contract": 1}
    assert report.malformed_line_count == 1
    assert report.total_line_count == 4


def test_evaluate_fallback_window_handles_missing_file(tmp_path: Path) -> None:
    report = evaluate_fallback_window(
        events_file=tmp_path / "missing.jsonl",
        window_days=14,
        now=datetime(2026, 3, 4, 12, 0, tzinfo=UTC),
    )
    assert report.events_file_found is False
    assert report.fallback_count == 0
    assert report.fallback_by_surface == {}
