"""Regression fixture: verify Ruff B006 (mutable-argument-default) is enforced.

B006 fires when a function uses a mutable literal or constructor as a default
argument value. Python evaluates defaults once at definition time, so shared
mutable state leaks across all calls that omit the argument.

This test proves that:
  1. The bad pattern (``def f(items=[]):``) is caught by the active ruff config.
  2. The correct pattern (``def f(items=None):`` with in-body init) passes lint.
  3. The rule covers mutable constructors (``dict()``, ``set()``) as well.

If this test fails, check that ``B006`` is not suppressed in ``pyproject.toml``
and that the ``"B"`` selector is present under ``[tool.ruff.lint] select``.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

_RUFF = Path(sys.executable).parent / "ruff"
_RULE = "B006"


def _lint(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as fh:
        fh.write(source)
        path = fh.name
    return subprocess.run(
        [str(_RUFF), "check", "--select", _RULE, path],
        capture_output=True,
        text=True,
        check=False,
    )


def test_mutable_list_default_is_rejected() -> None:
    """``def f(items=[]):`` must fail B006."""
    result = _lint("def f(items=[]): pass\n")
    assert result.returncode != 0, "B006 should have flagged a mutable list default"
    assert _RULE in result.stdout or _RULE in result.stderr


def test_mutable_dict_default_is_rejected() -> None:
    """``def f(data={}):`` must fail B006."""
    result = _lint("def f(data={}): pass\n")
    assert result.returncode != 0, "B006 should have flagged a mutable dict default"
    assert _RULE in result.stdout or _RULE in result.stderr


def test_mutable_set_constructor_is_rejected() -> None:
    """``def f(tags=set()):`` must fail B006."""
    result = _lint("def f(tags=set()): pass\n")
    assert result.returncode != 0, "B006 should have flagged a mutable set() default"
    assert _RULE in result.stdout or _RULE in result.stderr


def test_none_sentinel_passes() -> None:
    """``def f(items=None):`` with in-body init must pass B006."""
    source = "def f(items=None):\n    if items is None:\n        items = []\n    return items\n"
    result = _lint(source)
    assert result.returncode == 0, f"Correct sentinel pattern should pass B006:\n{result.stdout}"


def test_immutable_default_passes() -> None:
    """Non-mutable defaults (str, int, tuple, None) must pass B006."""
    source = (
        "def f(name='', count=0, pair=(1, 2), flag=None): pass\n"
    )
    result = _lint(source)
    assert result.returncode == 0, f"Immutable defaults should pass B006:\n{result.stdout}"
