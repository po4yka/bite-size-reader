from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _should_skip(path: Path, *, exclude_dirs: set[str]) -> bool:
    return any(part in exclude_dirs for part in path.parts)


def _is_text_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(8192)
    except OSError:
        return False

    return b"\0" not in sample


def _read_line_count(path: Path) -> int | None:
    if not _is_text_file(path):
        return None

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return None


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object mapping 'path' -> int")

    out: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, int):
            out[key] = value
    return out


def _iter_tracked_files(*, exclude_dirs: set[str]) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return _iter_files([Path(".")], exclude_dirs=exclude_dirs)

    files: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = Path(raw_path.decode("utf-8"))
        if path.is_file() and not _should_skip(path, exclude_dirs=exclude_dirs):
            files.append(path)
    return files


def _iter_files(roots: Iterable[Path], *, exclude_dirs: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if not _should_skip(root, exclude_dirs=exclude_dirs):
                files.append(root)
            continue

        if not root.exists():
            continue

        for path in root.rglob("*"):
            if path.is_file() and not _should_skip(path, exclude_dirs=exclude_dirs):
                files.append(path)
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail if any tracked text file exceeds a LOC threshold. Supports a baseline allowlist."
        )
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=1500,
        help="Maximum allowed file size in LOC (default: 1500).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional JSON baseline mapping 'path' -> allowed LOC.",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name(s) to exclude from scanning (can be repeated).",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to check (pre-commit passes changed files).",
    )

    args = parser.parse_args(argv)

    max_loc: int = args.max_loc
    if max_loc <= 0:
        print(f"Invalid --max-loc: {max_loc}", file=sys.stderr)
        return 2

    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS)
    exclude_dirs.update(args.exclude_dir)

    baseline: dict[str, int] = {}
    if args.baseline is not None:
        baseline = _load_baseline(args.baseline)

    if args.files:
        files = _iter_files((Path(path) for path in args.files), exclude_dirs=exclude_dirs)
    else:
        files = _iter_tracked_files(exclude_dirs=exclude_dirs)

    loc_by_file: dict[str, int] = {}
    for path in files:
        loc = _read_line_count(path)
        if loc is None:
            continue
        loc_by_file[path.as_posix()] = loc

    violations_new: list[tuple[str, int]] = []
    violations_grew: list[tuple[str, int, int]] = []

    for file_path, loc in sorted(loc_by_file.items()):
        if loc <= max_loc:
            continue
        allowed = baseline.get(file_path)
        if allowed is None:
            violations_new.append((file_path, loc))
        elif loc > allowed:
            violations_grew.append((file_path, loc, allowed))

    if not args.files:
        stale = [path for path in baseline if path not in loc_by_file]
        if stale:
            print(
                "warning: baseline contains entries that no longer exist (safe to remove):",
                file=sys.stderr,
            )
            for stale_path in sorted(stale):
                print(f"  - {stale_path}", file=sys.stderr)

    if violations_new or violations_grew:
        print(f"File size limit exceeded (> {max_loc} LOC):", file=sys.stderr)

        for file_path, loc in violations_new:
            print(f"  - NEW {file_path} ({loc} LOC)", file=sys.stderr)

        for file_path, loc, allowed in violations_grew:
            print(
                f"  - GREW {file_path} ({loc} LOC > baseline {allowed})",
                file=sys.stderr,
            )

        if args.baseline is not None:
            print(
                (
                    f"Baseline file: {args.baseline.as_posix()} "
                    "(reduce file size; don't bump baseline unless intentionally "
                    "accepting debt)."
                ),
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
