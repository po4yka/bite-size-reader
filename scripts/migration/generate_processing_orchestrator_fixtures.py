#!/usr/bin/env python3
"""Generate/check processing orchestrator parity fixtures from Python baselines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.migration.fixture_runner import parse_check_flag, run_fixture_cli
from app.migration.processing_orchestrator import (
    build_python_forward_processing_plan,
    build_python_url_processing_plan,
)

INPUT_DIR = Path("docs/migration/fixtures/processing_orchestrator/input")
EXPECTED_DIR = Path("docs/migration/fixtures/processing_orchestrator/expected")


def _build_expected(payload: dict[str, Any]) -> dict[str, Any]:
    fixture_type = str(payload.get("type") or "").strip()
    fixture_payload = payload.get("payload")
    if not isinstance(fixture_payload, dict):
        msg = "fixture payload must be a JSON object"
        raise ValueError(msg)

    if fixture_type == "url_plan":
        return build_python_url_processing_plan(fixture_payload)

    if fixture_type == "forward_plan":
        return build_python_forward_processing_plan(fixture_payload)

    msg = f"unsupported fixture type: {fixture_type}"
    raise ValueError(msg)


def _process_fixture(input_path: Path, *, check: bool) -> bool:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"fixture must be a JSON object: {input_path}")
        return False

    expected = _build_expected(payload)
    output_path = EXPECTED_DIR / f"{input_path.stem}.json"

    if check:
        if not output_path.exists():
            print(f"missing expected fixture: {output_path}")
            return False
        current = json.loads(output_path.read_text(encoding="utf-8"))
        if current != expected:
            print(f"stale expected fixture: {output_path}")
            return False
        return True

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output_path}")
    return True


def main() -> int:
    check = parse_check_flag(__doc__)
    return run_fixture_cli(
        input_dir=INPUT_DIR,
        process_fixture=_process_fixture,
        check=check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
