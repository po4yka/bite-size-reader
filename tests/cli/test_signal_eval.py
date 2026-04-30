from __future__ import annotations

import json
from pathlib import Path

from app.cli.signal_eval import compute_precision_at_k, load_eval_rows


def test_compute_precision_at_5_from_exported_eval_rows(tmp_path):
    path = tmp_path / "signals_eval.jsonl"
    rows = [
        {"signal_id": 1, "rank": 1, "relevant": True},
        {"signal_id": 2, "rank": 2, "relevant": False},
        {"signal_id": 3, "rank": 3, "relevant": True},
        {"signal_id": 4, "rank": 4, "relevant": False},
        {"signal_id": 5, "rank": 5, "relevant": True},
        {"signal_id": 6, "rank": 6, "relevant": True},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    loaded = load_eval_rows(path)
    result = compute_precision_at_k(loaded, k=5)

    assert result == {"k": 5, "evaluated": 5, "relevant": 3, "precision": 0.6}


def test_compute_precision_at_5_treats_liked_and_queued_as_relevant() -> None:
    rows = [
        {"signal_id": 1, "final_score": 0.9, "status": "liked"},
        {"signal_id": 2, "final_score": 0.8, "status": "queued"},
        {"signal_id": 3, "final_score": 0.7, "status": "dismissed"},
    ]

    result = compute_precision_at_k(rows, k=5)

    assert result == {"k": 5, "evaluated": 3, "relevant": 2, "precision": 2 / 3}


def test_compute_precision_at_5_from_checked_in_fixture() -> None:
    rows = load_eval_rows(Path("tests/fixtures/signal_eval_sample.jsonl"))

    result = compute_precision_at_k(rows, k=5)

    assert result["precision"] == 0.6
