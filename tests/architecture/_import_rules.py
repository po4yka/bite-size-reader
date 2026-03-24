from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def collect_forbidden_imports(
    root: Path,
    *,
    forbidden_prefixes: tuple[str, ...],
    ignored_path_prefixes: tuple[str, ...] = (),
) -> list[str]:
    violations: list[str] = []

    for path in sorted(root.rglob("*.py")):
        relative_path = path.relative_to(root.parent).as_posix()
        if relative_path.startswith(ignored_path_prefixes):
            continue

        module = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_prefixes):
                    violations.append(f"{relative_path}:{node.lineno} {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        violations.append(f"{relative_path}:{node.lineno} {alias.name}")

    return violations
