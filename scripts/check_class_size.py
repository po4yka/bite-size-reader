from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


@dataclass(frozen=True)
class ClassSpan:
    file: Path
    qualname: str
    lineno: int
    end_lineno: int

    @property
    def loc(self) -> int:
        return self.end_lineno - self.lineno + 1

    @property
    def key(self) -> str:
        return f"{self.file.as_posix()}::{self.qualname}"


class _ClassCollector(ast.NodeVisitor):
    def __init__(self, file: Path) -> None:
        self._file = file
        self._stack: list[str] = []
        self.classes: list[ClassSpan] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        name = getattr(node, "name", "<anonymous>")
        self._stack.append(name)

        lineno = int(getattr(node, "lineno", 1) or 1)
        end_lineno = getattr(node, "end_lineno", None)
        if isinstance(end_lineno, int) and end_lineno >= lineno:
            qualname = ".".join(self._stack)
            self.classes.append(
                ClassSpan(
                    file=self._file,
                    qualname=qualname,
                    lineno=lineno,
                    end_lineno=end_lineno,
                )
            )

        self.generic_visit(node)
        self._stack.pop()


def _should_skip(path: Path, *, exclude_dirs: set[str]) -> bool:
    return any(part in exclude_dirs for part in path.parts)


def _iter_py_files(roots: Iterable[Path], *, exclude_dirs: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            if root.suffix == ".py" and not _should_skip(root, exclude_dirs=exclude_dirs):
                files.append(root)
            continue

        if not root.exists():
            continue

        for p in root.rglob("*.py"):
            if not _should_skip(p, exclude_dirs=exclude_dirs):
                files.append(p)
    return files


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object mapping 'file::Class' -> int")
    out: dict[str, int] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, int):
            out[k] = v
    return out


def _collect_classes(files: list[Path]) -> list[ClassSpan]:
    classes: list[ClassSpan] = []
    for file in files:
        text = _read_text(file)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # If the environment Python can't parse the file (e.g. newer syntax),
            # skip here. CI/pre-commit run on the repo's target Python.
            continue

        collector = _ClassCollector(file=file)
        collector.visit(tree)
        classes.extend(collector.classes)
    return classes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if any Python class exceeds a LOC threshold. Supports a baseline allowlist."
    )
    parser.add_argument(
        "--max-loc",
        type=int,
        default=1000,
        help="Maximum allowed class size in LOC (default: 1000).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Optional JSON baseline mapping 'file::Class' -> allowed LOC (grandfathers existing large classes).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        action="append",
        default=[],
        help="Root(s) to scan when no filenames are provided (default: repository root).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Directory name(s) to exclude from scanning (can be repeated).",
    )
    parser.add_argument(
        "files", nargs="*", help="Files to check (pre-commit passes changed files)."
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

    roots: list[Path]
    if args.files:
        roots = [Path(p) for p in args.files]
    elif args.root:
        roots = args.root
    else:
        roots = [Path(".")]

    py_files = _iter_py_files(roots, exclude_dirs=exclude_dirs)
    class_spans = _collect_classes(py_files)

    # Index for stale baseline warnings
    present_keys = {c.key for c in class_spans}

    violations_new: list[ClassSpan] = []
    violations_grew: list[tuple[ClassSpan, int]] = []

    for c in class_spans:
        if c.loc <= max_loc:
            continue
        allowed = baseline.get(c.key)
        if allowed is None:
            violations_new.append(c)
        elif c.loc > allowed:
            violations_grew.append((c, allowed))

    # Only warn about stale baseline entries when scanning the whole repo (CI),
    # not when running on a subset of files (pre-commit).
    if not args.files:
        stale = [k for k in baseline if k not in present_keys]
        if stale:
            print(
                "warning: baseline contains entries that no longer exist (safe to remove):",
                file=sys.stderr,
            )
            for k in sorted(stale):
                print(f"  - {k}", file=sys.stderr)

    if violations_new or violations_grew:
        print(f"Class size limit exceeded (> {max_loc} LOC):", file=sys.stderr)

        for c in sorted(violations_new, key=lambda x: (x.file.as_posix(), x.qualname, x.lineno)):
            print(
                f"  - NEW {c.key} at {c.file.as_posix()}:{c.lineno} ({c.loc} LOC)",
                file=sys.stderr,
            )

        for c, allowed in sorted(
            violations_grew, key=lambda x: (x[0].file.as_posix(), x[0].qualname, x[0].lineno)
        ):
            print(
                f"  - GREW {c.key} at {c.file.as_posix()}:{c.lineno} ({c.loc} LOC > baseline {allowed})",
                file=sys.stderr,
            )

        if args.baseline is not None:
            print(
                f"Baseline file: {args.baseline.as_posix()} (reduce class size; don't bump baseline unless intentionally accepting debt).",
                file=sys.stderr,
            )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
