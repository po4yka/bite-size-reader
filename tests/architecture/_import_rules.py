from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
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
        for node in _iter_runtime_nodes(module):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_prefixes):
                    violations.append(f"{relative_path}:{node.lineno} {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        violations.append(f"{relative_path}:{node.lineno} {alias.name}")

    return violations


def _iter_runtime_nodes(module: ast.AST) -> Iterable[ast.AST]:
    """Walk ``module`` skipping the bodies of ``if TYPE_CHECKING:`` blocks.

    Imports guarded by ``TYPE_CHECKING`` are not executed at runtime, so they
    don't violate runtime layer boundaries.
    """
    from collections import deque

    stack: deque[ast.AST] = deque([module])
    while stack:
        node = stack.popleft()
        yield node
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(node, ast.If)
                and _is_type_checking_guard(node.test)
                and child in node.body
            ):
                continue
            stack.append(child)


def _is_type_checking_guard(test: ast.expr) -> bool:
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return True
    return False
