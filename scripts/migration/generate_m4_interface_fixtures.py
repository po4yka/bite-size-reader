#!/usr/bin/env python3
"""Generate/check M4 interface routing fixtures from Python baseline resolvers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.migration.interface_router import (
    build_python_mobile_route_decision,
    build_python_telegram_command_decision,
)

INPUT_DIR = Path("docs/migration/fixtures/m4_interface_routing/input")
EXPECTED_DIR = Path("docs/migration/fixtures/m4_interface_routing/expected")


def _build_expected(payload: dict[str, Any]) -> dict[str, Any]:
    fixture_type = str(payload.get("type") or "").strip()
    fixture_payload = payload.get("payload")
    if not isinstance(fixture_payload, dict):
        msg = "fixture payload must be an object"
        raise ValueError(msg)

    if fixture_type == "mobile_route":
        mobile_decision = build_python_mobile_route_decision(
            method=str(fixture_payload.get("method") or ""),
            path=str(fixture_payload.get("path") or ""),
        )
        return mobile_decision.to_mapping()

    if fixture_type == "telegram_command":
        command_decision = build_python_telegram_command_decision(
            text=str(fixture_payload.get("text") or "")
        )
        return command_decision.to_mapping()

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
