"""Regression fixture: verify Ruff B006 and B023 are enforced.

B006 fires when a function uses a mutable literal or constructor as a default
argument value. Python evaluates defaults once at definition time, so shared
mutable state leaks across all calls that omit the argument.

B023 fires when a lambda or nested function defined inside a loop references a
loop variable without early binding. All generated closures will see the
*final* loop value, not the value at creation time.

If either test class fails, check that the relevant rule is not suppressed in
``pyproject.toml`` and that the ``"B"`` selector is present under
``[tool.ruff.lint] select``.
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


# ---------------------------------------------------------------------------
# B023: function-uses-loop-variable
# ---------------------------------------------------------------------------

_B023 = "B023"


def _lint_b023(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as fh:
        fh.write(source)
        path = fh.name
    return subprocess.run(
        [str(_RUFF), "check", "--select", _B023, path],
        capture_output=True,
        text=True,
        check=False,
    )


def test_lambda_in_loop_referencing_loop_var_is_rejected() -> None:
    """``lambda: key`` inside a for loop must fail B023."""
    source = "fns = []\nfor key in keys:\n    fns.append(lambda: key)\n"
    result = _lint_b023(source)
    assert result.returncode != 0, "B023 should have flagged lambda closing over loop var"
    assert _B023 in result.stdout or _B023 in result.stderr


def test_nested_def_in_loop_referencing_loop_var_is_rejected() -> None:
    """Function def inside a for loop closing over the loop variable must fail B023."""
    source = (
        "cbs = []\n"
        "for item in items:\n"
        "    def handler():\n"
        "        return item\n"
        "    cbs.append(handler)\n"
    )
    result = _lint_b023(source)
    assert result.returncode != 0, "B023 should have flagged nested def closing over loop var"
    assert _B023 in result.stdout or _B023 in result.stderr


def test_default_arg_binding_passes_b023() -> None:
    """``lambda key=key: key`` binds the value at definition time — must pass B023."""
    source = "fns = []\nfor key in keys:\n    fns.append(lambda key=key: key)\n"
    result = _lint_b023(source)
    assert result.returncode == 0, f"Default-arg binding must pass B023:\n{result.stdout}"


def test_sort_key_lambda_passes_b023() -> None:
    """``key=lambda x: x.attr`` in a sort call uses its own arg — must pass B023."""
    source = "for group in groups:\n    group.sort(key=lambda item: item.score)\n"
    result = _lint_b023(source)
    assert result.returncode == 0, f"Sort key lambda must pass B023:\n{result.stdout}"
