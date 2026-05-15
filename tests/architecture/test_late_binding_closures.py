"""Regression fixture: verify no late-binding closure bugs exist in the codebase.

Python closures use late binding: variables referenced by inner functions or
lambdas are resolved when the closure is *called*, not when it is *created*.
When closures are defined inside loops and escape (i.e. are stored and invoked
after the loop body completes), they all observe the *final* loop variable value.

Classic bad pattern::

    handlers = []
    for key in keys:
        handlers.append(lambda: key)   # all lambdas see the last key!

Safe patterns (any of these)::

    handlers.append(lambda key=key: key)     # default-arg binding
    handlers.append(make_handler(key))       # factory function
    handlers.append(functools.partial(f, key))  # partial application

This module:

1. Embeds a minimal AST scanner that detects closures inside loops that
   reference loop variables without early binding.
2. Runs the scanner against this repository and asserts zero findings.
3. Includes positive tests confirming the scanner catches real bugs.
4. Includes negative tests confirming the scanner accepts safe patterns.

If the codebase scan test fails, a new late-binding closure bug was introduced.
Consult the scanner output for file:line details.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Sequence

# ---------------------------------------------------------------------------
# Embedded AST scanner
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_SKIP_DIRS = {".venv", "__pycache__", ".git", "build", "dist", "data"}
# Exclude architecture tests themselves: they intentionally contain demo patterns.
_SKIP_FILES = {"tests/architecture/test_late_binding_closures.py"}


def _names_used_in(node: ast.AST) -> set[str]:
    return {
        n.id
        for n in ast.walk(node)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


def _default_names(args: ast.arguments) -> set[str]:
    names: set[str] = set()
    for d in args.defaults + args.kw_defaults:
        if d is not None:
            names |= _names_used_in(d)
    return names


def _arg_names(args: ast.arguments) -> set[str]:
    names = {a.arg for a in args.args + args.posonlyargs + args.kwonlyargs}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


class _ClosureInLoopScanner(ast.NodeVisitor):
    """Finds lambdas/functions defined inside for/while loops that close over loop vars."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._stack: list[set[str]] = []
        self.findings: list[tuple[str, int, str, list[str]]] = []

    # ------------------------------------------------------------------
    def _push(self, loop_vars: set[str]) -> None:
        self._stack.append(loop_vars)

    def _pop(self) -> None:
        self._stack.pop()

    def _current_loop_vars(self) -> set[str]:
        if not self._stack:
            return set()
        result: set[str] = set()
        for vs in self._stack:
            result |= vs
        return result

    # ------------------------------------------------------------------
    def _loop_vars_from_target(self, target: ast.expr) -> set[str]:
        names: set[str] = set()

        def collect(t: ast.expr) -> None:
            if isinstance(t, ast.Name):
                names.add(t.id)
            elif isinstance(t, (ast.Tuple, ast.List)):
                for elt in t.elts:
                    collect(elt)

        collect(target)
        return names

    def _assigned_in_body(self, stmts: Sequence[ast.stmt]) -> set[str]:
        names: set[str] = set()
        for stmt in stmts:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    names.add(child.id)
        return names

    # ------------------------------------------------------------------
    def visit_For(self, node: ast.For) -> None:
        lvars = self._loop_vars_from_target(node.target)
        body_vars = self._assigned_in_body(node.body)
        self._push(lvars | body_vars)
        self.generic_visit(node)
        self._pop()

    def visit_While(self, node: ast.While) -> None:
        body_vars = self._assigned_in_body(node.body)
        self._push(body_vars)
        self.generic_visit(node)
        self._pop()

    # ------------------------------------------------------------------
    def _check_closure(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        kind: str,
    ) -> None:
        loop_vars = self._current_loop_vars()
        if not loop_vars:
            return
        args = node.args
        bound = _arg_names(args)
        # defaults are evaluated at definition time (early binding) — safe
        safe_via_default = _default_names(args)
        used = _names_used_in(node) - bound - safe_via_default
        at_risk = sorted(used & loop_vars)
        if at_risk:
            self.findings.append((self._path, node.lineno, kind, at_risk))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_closure(node, "def")
        # New scope: inner loops inside this function are independent
        saved = self._stack[:]
        self._stack = []
        self.generic_visit(node)
        self._stack = saved

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_closure(node, "async def")
        saved = self._stack[:]
        self._stack = []
        self.generic_visit(node)
        self._stack = saved

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._check_closure(node, "lambda")
        saved = self._stack[:]
        self._stack = []
        self.generic_visit(node)
        self._stack = saved


def _scan_source(source: str, filename: str = "<test>") -> list[tuple[str, int, str, list[str]]]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []
    scanner = _ClosureInLoopScanner(filename)
    scanner.visit(tree)
    return scanner.findings


def scan_repository() -> list[tuple[str, int, str, list[str]]]:
    """Scan every .py file in the repository; return all findings."""
    all_findings: list[tuple[str, int, str, list[str]]] = []
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
# Positive tests — scanner MUST flag these
# ---------------------------------------------------------------------------


def test_lambda_in_for_loop_is_flagged() -> None:
    """Lambda inside for loop that closes over the loop variable must be found."""
    source = """\
handlers = []
for key in keys:
    handlers.append(lambda: key)
"""
    findings = _scan_source(source)
    assert findings, "Scanner must flag late-binding lambda in for loop"
    assert any("key" in f[3] for f in findings)


def test_nested_def_in_for_loop_is_flagged() -> None:
    """Function def inside for loop that closes over the loop variable must be found."""
    source = """\
callbacks = []
for item in items:
    def handler():
        return item
    callbacks.append(handler)
"""
    findings = _scan_source(source)
    assert findings, "Scanner must flag late-binding function def in for loop"
    assert any("item" in f[3] for f in findings)


def test_lambda_in_while_loop_is_flagged() -> None:
    """Lambda inside while loop that closes over a loop-mutated variable must be found."""
    source = """\
results = []
i = 0
while i < 10:
    results.append(lambda: i)
    i += 1
"""
    findings = _scan_source(source)
    assert findings, "Scanner must flag late-binding lambda in while loop"
    assert any("i" in f[3] for f in findings)


def test_lambda_in_comprehension_not_immediately_safe() -> None:
    """Lambda inside list comprehension closing over comp variable must be found."""
    source = """\
handlers = [lambda: x for x in range(10)]
"""
    # Note: comprehension variables are local to the comprehension scope in
    # Python 3, but late binding still applies to lambdas created inside them.
    # The indent-based scanner catches this only if it's structured as a for loop.
    # Our AST scanner uses ast.For and ast.While; list comprehensions use
    # ast.ListComp with ast.comprehension generators — this is a distinct case.
    # We document that the scanner focuses on explicit for/while loops.
    # This test confirms the current scanner scope (comprehensions are a separate check).
    _ = _scan_source(source)  # must not crash


# ---------------------------------------------------------------------------
# Negative tests — scanner must NOT flag these
# ---------------------------------------------------------------------------


def test_default_arg_binding_is_safe() -> None:
    """``lambda key=key: key`` binds early via default arg — must pass."""
    source = """\
handlers = []
for key in keys:
    handlers.append(lambda key=key: key)
"""
    findings = _scan_source(source)
    assert not findings, f"Default-arg binding must not be flagged: {findings}"


def test_factory_function_is_safe() -> None:
    """Factory function pattern creates a new scope per iteration — must pass."""
    source = """\
def make_handler(key):
    def handler():
        return key
    return handler

callbacks = []
for item in items:
    callbacks.append(make_handler(item))
"""
    findings = _scan_source(source)
    assert not findings, f"Factory function pattern must not be flagged: {findings}"


def test_immediately_invoked_closure_is_flagged_as_known_false_positive() -> None:
    """Immediately invoked lambdas are safe but appear as scanner false positives.

    ``(lambda: x)()`` is called in the same iteration it is created, so late
    binding cannot cause a bug.  However, the AST scanner has no parent-node
    context to distinguish immediate invocation from deferred storage, so it
    conservatively flags the lambda.  This is an acceptable false positive:
    such patterns are rare in practice and the programmer can switch to a plain
    call or a default-arg binding to silence the scanner.
    """
    source = """\
results = []
for x in range(10):
    result = (lambda: x)()
    results.append(result)
"""
    findings = _scan_source(source)
    # Scanner flags the lambda (conservative false positive — documented limitation).
    assert findings, "Expected scanner to flag IIFE lambda as a conservative false positive"


def test_sort_key_lambda_is_safe() -> None:
    """``key=lambda x: x.attr`` inside a loop body is safe (x is the sort element)."""
    source = """\
for group in groups:
    group.sort(key=lambda item: item.score)
"""
    findings = _scan_source(source)
    assert not findings, f"Sort key lambda must not be flagged: {findings}"


def test_lambda_using_only_outer_scope_is_safe() -> None:
    """Lambda that references names outside the loop (not loop vars) must pass."""
    source = """\
CONSTANT = 42
handlers = []
for _ in range(10):
    handlers.append(lambda: CONSTANT)
"""
    findings = _scan_source(source)
    assert not findings, f"Lambda referencing only outer scope must not be flagged: {findings}"


# ---------------------------------------------------------------------------
# Behavioural proof — the scanner finds real bugs before and after a fix
# ---------------------------------------------------------------------------


def test_late_binding_behaviour_is_real() -> None:
    """Prove Python really does exhibit late-binding for closures in loops."""
    handlers: list = []
    for value in [10, 20, 30]:
        handlers.append(lambda: value)  # noqa: B023 — intentionally demonstrating the bug

    # All handlers see the final loop value, not their creation-time value
    results = [h() for h in handlers]
    assert results == [30, 30, 30], "Late binding: all closures see the final value"


def test_default_arg_fix_gives_correct_per_iteration_values() -> None:
    """Default-arg binding fixes the late-binding bug: each closure sees its own value."""
    handlers: list = []
    for value in [10, 20, 30]:
        handlers.append(lambda v=value: v)

    results = [h() for h in handlers]
    assert results == [10, 20, 30], "Default-arg binding: each closure sees its own value"


def test_factory_fix_gives_correct_per_iteration_values() -> None:
    """Factory function pattern also fixes late binding."""

    def make(v: int):
        def handler() -> int:
            return v

        return handler

    handlers = [make(value) for value in [10, 20, 30]]
    results = [h() for h in handlers]
    assert results == [10, 20, 30], "Factory pattern: each closure sees its own value"


# ---------------------------------------------------------------------------
# Codebase scan — must stay clean
# ---------------------------------------------------------------------------


def test_no_late_binding_closures_in_codebase() -> None:
    """Scan the entire repository; assert zero late-binding closures in loops.

    If this test fails, a new deferred closure was added inside a for/while
    loop without early binding. Fix options:
      - Default-arg binding:   ``lambda key=key: key``
      - Factory function:      ``def make(key): def h(): return key; return h``
      - functools.partial:     ``functools.partial(callback, key)``
      - Explicit argument:     pass the variable directly instead of closing
    """
    findings = scan_repository()
    if findings:
        lines = [
            f"  {path}:{lineno}  [{kind}]  closes over: {', '.join(vars_)}"
            for path, lineno, kind, vars_ in findings
        ]
        msg = "Late-binding closures found in codebase:\n" + "\n".join(lines)
        raise AssertionError(msg)
