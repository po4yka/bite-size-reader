"""Shared helper for migration fixture generator/check scripts."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    ProcessFixture = Callable[..., bool]
else:
    ProcessFixture = object


def parse_check_flag(description: str | None) -> bool:
    """Parse shared `--check` CLI flag used by fixture scripts."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--check", action="store_true", help="Verify fixtures are up to date")
    return bool(parser.parse_args().check)


def run_fixture_cli(
    *,
    input_dir: Path,
    process_fixture: ProcessFixture,
    check: bool,
) -> int:
    """Run fixture generation/check loop and return process exit code."""
    input_files = sorted(input_dir.glob("*.json"))
    if not input_files:
        print(f"no input fixtures found in {input_dir}")
        return 1

    ok = True
    for input_path in input_files:
        ok = process_fixture(input_path, check=check) and ok

    if check:
        print("fixtures up to date" if ok else "fixtures need regeneration")

    return 0 if ok else 1
