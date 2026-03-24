from __future__ import annotations

import ast
from pathlib import Path


def test_domain_layer_has_no_outer_layer_imports() -> None:
    domain_root = Path(__file__).resolve().parents[2] / "app" / "domain"
    forbidden_prefixes = (
        "app.api",
        "app.db",
        "app.infrastructure",
        "app.adapters",
        "app.di",
    )

    violations: list[str] = []
    for path in domain_root.rglob("*.py"):
        module = ast.parse(path.read_text())
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_prefixes):
                    violations.append(
                        f"{path.relative_to(domain_root.parent)}:{node.lineno} {node.module}"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        violations.append(
                            f"{path.relative_to(domain_root.parent)}:{node.lineno} {alias.name}"
                        )

    assert violations == []
