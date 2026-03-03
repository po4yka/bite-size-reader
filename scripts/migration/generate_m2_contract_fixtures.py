#!/usr/bin/env python3
"""Generate M2 summary-contract parity fixture expectations from Python baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.core.summary_contract_impl.contract import validate_and_shape_summary

INPUT_DIR = Path("docs/migration/fixtures/m2_summary_contract/input")
EXPECTED_DIR = Path("docs/migration/fixtures/m2_summary_contract/expected")

SUBSET_KEYS = [
    "summary_250",
    "summary_1000",
    "tldr",
    "key_ideas",
    "topic_tags",
    "entities",
    "estimated_reading_time_min",
    "key_stats",
    "questions_answered",
    "topic_taxonomy",
    "article_id",
    "source_type",
    "temporal_freshness",
    "hallucination_risk",
    "confidence",
    "forwarded_post_extras",
]


def _shape_signature(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "bool"}
    if isinstance(value, int | float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        if not value:
            return {"type": "array", "item": {"type": "any"}}

        variants: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in value:
            shape = _shape_signature(item)
            signature = json.dumps(shape, sort_keys=True, ensure_ascii=False)
            if signature in seen:
                continue
            seen.add(signature)
            variants.append(shape)

        item_shape: dict[str, Any] = (
            variants[0] if len(variants) == 1 else {"type": "union", "variants": variants}
        )

        return {"type": "array", "item": item_shape}
    if isinstance(value, dict):
        return {
            "type": "object",
            "fields": {k: _shape_signature(v) for k, v in sorted(value.items())},
        }

    return {"type": type(value).__name__}


def _build_expected(payload: dict[str, Any]) -> dict[str, Any]:
    shaped = validate_and_shape_summary(payload)
    return {
        "shape": _shape_signature(shaped),
        "subset": {key: shaped.get(key) for key in SUBSET_KEYS},
    }


def _process_fixture(input_path: Path, *, check: bool) -> bool:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
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
