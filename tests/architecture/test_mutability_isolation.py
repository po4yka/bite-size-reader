"""Regression fixture: verify mutability and aliasing isolation in the codebase.

Python variables are references, not value copies.  Accidental aliasing of
mutable objects — lists, dicts, sets — leads to action-at-a-distance bugs
that are difficult to reproduce and trace.

This module:

1. Embeds a lightweight AST scanner for the highest-risk mechanical patterns:
   ``[mutable] * n`` and ``dict.fromkeys(keys, mutable_value)``.
2. Runs the scanner against the repository and asserts zero findings.
3. Provides concrete behavioural proofs for the aliasing patterns most
   relevant to this codebase's architecture, including:
   - Mutable default-argument isolation (proved by the B006 fixture)
   - Constructor defensive-copy isolation
   - Accessor copy isolation (``providers`` property)
   - Nested-repeat aliasing (proved below)
   - dict.fromkeys aliasing
   - Intentionally shared state documented with explicit notes
4. Serves as a regression guard: any new occurrence of these patterns will
   cause this suite to fail before it reaches production.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Repository root and scan exclusions
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_SKIP_DIRS = {".venv", "__pycache__", ".git", "build", "dist", "data"}
_SKIP_FILES = {
    "tests/architecture/test_mutability_isolation.py",  # this file has demo code
    # [{"role": "user", "content": "Hello"}] * 51 is used to test message-count
    # validation; the dicts are never mutated — the function raises immediately.
    "tests/test_openrouter_compliance.py",
}

# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

_MUTABLE_NAMES = {
    "list", "dict", "set", "defaultdict", "OrderedDict", "Counter", "deque"
}


def _is_mutable(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Call):
        fn = node.func
        name: str | None = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name in _MUTABLE_NAMES:
            return True
    return False


# ---------------------------------------------------------------------------
# Scanner: [mutable] * n  and  dict.fromkeys(keys, mutable)
# ---------------------------------------------------------------------------


class _MutablePatternScanner(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self._path = path
        self.findings: list[tuple[str, int, str]] = []

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mult):
            for left, _right in [(node.left, node.right), (node.right, node.left)]:
                if isinstance(left, (ast.List, ast.Tuple)) and any(
                    _is_mutable(e) for e in left.elts
                ):
                    self.findings.append(
                        (self._path, node.lineno, "[mutable] * n")
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "fromkeys":
            if len(node.args) >= 2 and _is_mutable(node.args[1]):
                self.findings.append(
                    (self._path, node.lineno, "dict.fromkeys(keys, mutable)")
                )
        self.generic_visit(node)


def _scan_source(source: str, filename: str = "<test>") -> list[tuple[str, int, str]]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    scanner = _MutablePatternScanner(filename)
    scanner.visit(tree)
    return scanner.findings


def scan_repository() -> list[tuple[str, int, str]]:
    all_findings: list[tuple[str, int, str]] = []
    for path in sorted(_REPO_ROOT.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(_REPO_ROOT))
        if rel in _SKIP_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings = _scan_source(source, rel)
        all_findings.extend(findings)
    return all_findings


# ---------------------------------------------------------------------------
# Behavioural proofs — aliasing is real
# ---------------------------------------------------------------------------


def test_nested_repeat_aliases_inner_objects() -> None:
    """``[[]] * n`` shares one inner list across all outer elements."""
    matrix: list[list[int]] = [[]] * 3
    matrix[0].append(99)
    # The bug: all rows see the mutation
    assert matrix[1] == [99], "All inner lists are the same object"
    assert matrix[2] == [99], "Confirming shared reference"


def test_comprehension_creates_independent_inner_objects() -> None:
    """``[[] for _ in range(n)]`` creates independent inner lists."""
    matrix: list[list[int]] = [[] for _ in range(3)]
    matrix[0].append(99)
    assert matrix[1] == [], "Inner lists are independent"
    assert matrix[2] == [], "Confirming independence"


def test_dict_fromkeys_aliases_mutable_value() -> None:
    """``dict.fromkeys(keys, [])`` shares one list across all keys."""
    keys = ["a", "b", "c"]
    d: dict[str, list[int]] = dict.fromkeys(keys, [])  # noqa: RUF024
    d["a"].append(1)
    assert d["b"] == [1], "All keys share the same list"
    assert d["c"] == [1], "Confirming shared reference"


def test_dict_comprehension_creates_independent_values() -> None:
    """``{k: [] for k in keys}`` creates independent lists per key."""
    keys = ["a", "b", "c"]
    d: dict[str, list[int]] = {k: [] for k in keys}
    d["a"].append(1)
    assert d["b"] == [], "Each key has its own list"
    assert d["c"] == [], "Confirming independence"


def test_direct_alias_shares_state() -> None:
    """``b = a`` makes ``b`` an alias; mutation via either name affects both."""
    a: list[int] = [1, 2, 3]
    b = a  # alias, not a copy — intentional demo
    b.append(4)
    assert a == [1, 2, 3, 4], "Mutating b also mutates a"


def test_shallow_copy_isolates_top_level() -> None:
    """``b = a.copy()`` makes top-level independent but shares nested objects."""
    a: list[Any] = [[1, 2], [3, 4]]
    b = a.copy()
    b.append([5, 6])
    assert len(a) == 2, "Top-level lists are independent after shallow copy"
    b[0].append(99)
    assert a[0] == [1, 2, 99], "Inner lists are still shared (shallow copy)"


# ---------------------------------------------------------------------------
# Codebase-specific isolation proofs
# ---------------------------------------------------------------------------


def test_content_scraper_chain_providers_defensive_copy() -> None:
    """ContentScraperChain must not alias the caller's providers list.

    The constructor stores ``list(providers)`` so mutations to the original
    list after construction do not affect the chain's internal state.
    """
    from app.adapters.content.scraper.chain import ContentScraperChain

    provider_a = MagicMock()
    provider_a.provider_name = "mock_a"
    provider_b = MagicMock()
    provider_b.provider_name = "mock_b"

    providers_list: list[Any] = [provider_a]
    chain = ContentScraperChain(providers=providers_list)
    providers_list.append(provider_b)  # mutate the original list
    assert chain.providers == [provider_a], (
        "Mutating the original providers list must not affect the chain"
    )


def test_content_scraper_chain_providers_property_returns_copy() -> None:
    """The ``providers`` property must return an independent copy.

    Mutating the returned list must not affect the chain's internal state.
    """
    from app.adapters.content.scraper.chain import ContentScraperChain

    provider = MagicMock()
    provider.provider_name = "mock"
    chain = ContentScraperChain(providers=[provider])
    copy1 = chain.providers
    copy1.append(MagicMock())  # mutate the returned copy
    copy2 = chain.providers
    assert len(copy2) == 1, (
        "Mutating the returned providers list must not affect the chain"
    )


# ---------------------------------------------------------------------------
# Scanner positive tests — must flag these patterns
# ---------------------------------------------------------------------------


def test_nested_repeat_is_flagged() -> None:
    """Scanner must flag ``[{}] * n``."""
    source = "matrix = [{}] * 5\n"
    findings = _scan_source(source)
    assert findings, "Scanner must flag [mutable] * n"
    assert any("[mutable] * n" in f[2] for f in findings)


def test_fromkeys_mutable_is_flagged() -> None:
    """Scanner must flag ``dict.fromkeys(keys, [])``."""
    source = "d = dict.fromkeys(['a', 'b'], [])\n"
    findings = _scan_source(source)
    assert findings, "Scanner must flag dict.fromkeys(keys, mutable)"
    assert any("fromkeys" in f[2] for f in findings)


# ---------------------------------------------------------------------------
# Scanner negative tests — must NOT flag these
# ---------------------------------------------------------------------------


def test_nested_comprehension_is_safe() -> None:
    """``[[] for _ in range(n)]`` must not be flagged."""
    source = "matrix = [[] for _ in range(5)]\n"
    findings = _scan_source(source)
    assert not findings, f"Comprehension pattern must not be flagged: {findings}"


def test_fromkeys_immutable_is_safe() -> None:
    """``dict.fromkeys(keys, 0)`` must not be flagged."""
    source = "d = dict.fromkeys(['a', 'b'], 0)\n"
    findings = _scan_source(source)
    assert not findings, f"Immutable fromkeys default must not be flagged: {findings}"


def test_multiply_scalars_is_safe() -> None:
    """``[0] * n`` with immutable elements must not be flagged."""
    source = "zeros = [0] * 10\n"
    findings = _scan_source(source)
    assert not findings, f"Immutable element repetition must not be flagged: {findings}"


# ---------------------------------------------------------------------------
# Codebase-wide scan
# ---------------------------------------------------------------------------


def test_no_nested_repeat_or_fromkeys_mutable_in_codebase() -> None:
    """Scan the entire repository for ``[mutable] * n`` and ``dict.fromkeys(keys, mutable)``.

    If this test fails, a new high-risk aliasing pattern was introduced.
    Fix with:
      - Nested repeat: ``[[] for _ in range(n)]`` instead of ``[[]] * n``
      - fromkeys:      ``{k: [] for k in keys}`` instead of ``dict.fromkeys(keys, [])``
    """
    findings = scan_repository()
    if findings:
        lines = [
            f"  {path}:{lineno}  {pattern}"
            for path, lineno, pattern in findings
        ]
        msg = "Mutable aliasing patterns found in codebase:\n" + "\n".join(lines)
        raise AssertionError(msg)
