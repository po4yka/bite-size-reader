#!/usr/bin/env python3
"""Generate/check M3 pipeline shadow parity fixtures from Python snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.migration.pipeline_shadow import (
    build_python_chunking_preprocess_snapshot_from_input,
    build_python_content_cleaner_snapshot_from_input,
    build_python_extraction_adapter_snapshot,
    build_python_llm_wrapper_plan_snapshot_from_input,
)

INPUT_DIR = Path("docs/migration/fixtures/m3_pipeline_shadow/input")
EXPECTED_DIR = Path("docs/migration/fixtures/m3_pipeline_shadow/expected")


def _build_expected(fixture_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if fixture_name == "extraction_adapter":
        return build_python_extraction_adapter_snapshot(
            url_hash=str(payload.get("url_hash") or ""),
            content_text=str(payload.get("content_text") or ""),
            content_source=payload.get("content_source")
            if isinstance(payload.get("content_source"), str)
            else None,
            title=payload.get("title") if isinstance(payload.get("title"), str) else None,
            images_count=int(payload.get("images_count") or 0),
        )

    if fixture_name == "chunking_preprocess":
        return build_python_chunking_preprocess_snapshot_from_input(payload)

    if fixture_name == "llm_wrapper_plan":
        return build_python_llm_wrapper_plan_snapshot_from_input(payload)

    if fixture_name == "content_cleaner":
        return build_python_content_cleaner_snapshot_from_input(payload)

    msg = f"unknown fixture name: {fixture_name}"
    raise ValueError(msg)


def _process_fixture(input_path: Path, *, check: bool) -> bool:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"fixture must be a JSON object: {input_path}")
        return False

    expected = _build_expected(input_path.stem, payload)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify fixtures are up to date")
    args = parser.parse_args()

    input_files = sorted(INPUT_DIR.glob("*.json"))
    if not input_files:
        print(f"no input fixtures found in {INPUT_DIR}")
        return 1

    ok = True
    for input_path in input_files:
        ok = _process_fixture(input_path, check=args.check) and ok

    if args.check:
        print("fixtures up to date" if ok else "fixtures need regeneration")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
