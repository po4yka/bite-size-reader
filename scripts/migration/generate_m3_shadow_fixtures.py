#!/usr/bin/env python3
"""Generate/check M3 pipeline shadow parity fixtures from Python snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.migration.fixture_runner import parse_check_flag, run_fixture_cli
from app.migration.pipeline_shadow import (
    build_python_chunk_sentence_plan_snapshot_from_input,
    build_python_chunk_synthesis_prompt_snapshot_from_input,
    build_python_chunking_preprocess_snapshot_from_input,
    build_python_content_cleaner_snapshot_from_input,
    build_python_extraction_adapter_snapshot,
    build_python_llm_wrapper_plan_snapshot_from_input,
    build_python_summary_aggregate_snapshot_from_input,
    build_python_summary_user_content_snapshot_from_input,
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

    if fixture_name == "chunk_sentence_plan":
        return build_python_chunk_sentence_plan_snapshot_from_input(payload)

    if fixture_name == "llm_wrapper_plan":
        return build_python_llm_wrapper_plan_snapshot_from_input(payload)

    if fixture_name == "content_cleaner":
        return build_python_content_cleaner_snapshot_from_input(payload)

    if fixture_name == "summary_aggregate":
        return build_python_summary_aggregate_snapshot_from_input(payload)

    if fixture_name == "chunk_synthesis_prompt":
        return build_python_chunk_synthesis_prompt_snapshot_from_input(payload)

    if fixture_name == "summary_user_content":
        return build_python_summary_user_content_snapshot_from_input(payload)

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
    check = parse_check_flag(__doc__)
    return run_fixture_cli(
        input_dir=INPUT_DIR,
        process_fixture=_process_fixture,
        check=check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
