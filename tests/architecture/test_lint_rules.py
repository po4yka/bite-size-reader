"""Regression fixture: verify Ruff B006, B023, E711, and F632 are enforced.

B006 fires when a function uses a mutable literal or constructor as a default
argument value. Python evaluates defaults once at definition time, so shared
mutable state leaks across all calls that omit the argument.

B023 fires when a lambda or nested function defined inside a loop references a
loop variable without early binding. All generated closures will see the
*final* loop value, not the value at creation time.

E711 fires when ``== None`` or ``!= None`` is used instead of the correct
singleton comparison ``is None`` / ``is not None``. ``None`` is a singleton;
equality comparison can call a custom ``__eq__`` and produces unexpected results
with numpy arrays, SQLAlchemy column expressions, and other domain objects.

F632 fires when ``is`` or ``is not`` is used to compare against a literal value
(string, int, float, bytes, …). Python ``is`` checks object identity, not
value equality, so ``x is "ok"`` may silently return ``False`` even when the
strings are equal but stored as different objects.

If any test in this module fails, check that the relevant rule is not suppressed
in ``pyproject.toml`` and that the corresponding selector is present under
``[tool.ruff.lint] select`` (``"B"`` for B006/B023, ``"E"`` for E711,
``"F"`` for F632).
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


# ---------------------------------------------------------------------------
# F632: is-literal (use == to compare constant literals)
# ---------------------------------------------------------------------------

_F632 = "F632"


def _lint_f632(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as fh:
        fh.write(source)
        path = fh.name
    return subprocess.run(
        [str(_RUFF), "check", "--select", _F632, path],
        capture_output=True,
        text=True,
        check=False,
    )


def test_is_string_literal_is_rejected() -> None:
    """``x is "ok"`` must fail F632 — use ``x == "ok"``."""
    result = _lint_f632('x = "ok"\nassert x is "ok"\n')
    assert result.returncode != 0, "F632 should have flagged `x is <string>`"
    assert _F632 in result.stdout or _F632 in result.stderr


def test_is_not_string_literal_is_rejected() -> None:
    """``x is not "ok"`` must fail F632 — use ``x != "ok"``."""
    result = _lint_f632('x = "ok"\nassert x is not "ok"\n')
    assert result.returncode != 0, "F632 should have flagged `x is not <string>`"
    assert _F632 in result.stdout or _F632 in result.stderr


def test_is_int_literal_is_rejected() -> None:
    """``status is 200`` must fail F632 — use ``status == 200``."""
    result = _lint_f632("status = 200\nassert status is 200\n")
    assert result.returncode != 0, "F632 should have flagged `status is 200`"
    assert _F632 in result.stdout or _F632 in result.stderr


def test_is_bytes_literal_is_rejected() -> None:
    """``value is b"abc"`` must fail F632 — use ``value == b"abc"``."""
    result = _lint_f632('value = b"abc"\nassert value is b"abc"\n')
    assert result.returncode != 0, "F632 should have flagged `value is b\"abc\"`"
    assert _F632 in result.stdout or _F632 in result.stderr


def test_is_none_passes_f632() -> None:
    """``x is None`` is the correct singleton check — must pass F632."""
    result = _lint_f632("x = None\nassert x is None\n")
    assert result.returncode == 0, f"Singleton `is None` must pass F632:\n{result.stdout}"


def test_is_not_none_passes_f632() -> None:
    """``x is not None`` is the correct singleton check — must pass F632."""
    result = _lint_f632("x = None\nassert x is not None\n")
    assert result.returncode == 0, f"Singleton `is not None` must pass F632:\n{result.stdout}"


def test_equality_string_passes_f632() -> None:
    """``x == "ok"`` is correct value comparison — must pass F632."""
    result = _lint_f632('x = "ok"\nassert x == "ok"\n')
    assert result.returncode == 0, f"Value equality must pass F632:\n{result.stdout}"


def test_equality_int_passes_f632() -> None:
    """``status == 200`` is correct value comparison — must pass F632."""
    result = _lint_f632("status = 200\nassert status == 200\n")
    assert result.returncode == 0, f"Value equality must pass F632:\n{result.stdout}"


def test_sentinel_object_passes_f632() -> None:
    """``value is MISSING`` with a private sentinel object must pass F632."""
    source = "MISSING = object()\nvalue = MISSING\nassert value is MISSING\n"
    result = _lint_f632(source)
    assert result.returncode == 0, f"Sentinel identity check must pass F632:\n{result.stdout}"


# ---------------------------------------------------------------------------
# E711: comparison-to-None  (use is / is not, not == / !=)
# ---------------------------------------------------------------------------

_E711 = "E711"


def _lint_e711(source: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as fh:
        fh.write(source)
        path = fh.name
    return subprocess.run(
        [str(_RUFF), "check", "--select", _E711, path],
        capture_output=True,
        text=True,
        check=False,
    )


def test_eq_none_is_rejected() -> None:
    """``x == None`` must fail E711 — use ``x is None``."""
    result = _lint_e711("x = None\nassert x == None\n")
    assert result.returncode != 0, "E711 should have flagged `x == None`"
    assert _E711 in result.stdout or _E711 in result.stderr


def test_neq_none_is_rejected() -> None:
    """``x != None`` must fail E711 — use ``x is not None``."""
    result = _lint_e711("x = None\nassert x != None\n")
    assert result.returncode != 0, "E711 should have flagged `x != None`"
    assert _E711 in result.stdout or _E711 in result.stderr


def test_none_eq_x_is_rejected() -> None:
    """``None == x`` must fail E711 — use ``x is None``."""
    result = _lint_e711("x = None\nassert None == x\n")
    assert result.returncode != 0, "E711 should have flagged `None == x`"
    assert _E711 in result.stdout or _E711 in result.stderr


def test_none_neq_x_is_rejected() -> None:
    """``None != x`` must fail E711 — use ``x is not None``."""
    result = _lint_e711("x = None\nassert None != x\n")
    assert result.returncode != 0, "E711 should have flagged `None != x`"
    assert _E711 in result.stdout or _E711 in result.stderr


def test_is_none_passes_e711() -> None:
    """``x is None`` is the correct singleton check — must pass E711."""
    result = _lint_e711("x = None\nassert x is None\n")
    assert result.returncode == 0, f"Singleton `is None` must pass E711:\n{result.stdout}"


def test_is_not_none_passes_e711() -> None:
    """``x is not None`` is the correct singleton check — must pass E711."""
    result = _lint_e711("x = 1\nassert x is not None\n")
    assert result.returncode == 0, f"Singleton `is not None` must pass E711:\n{result.stdout}"


# ---------------------------------------------------------------------------
# Behavioural proof — E711/E711 rules guard real bugs
# ---------------------------------------------------------------------------


def test_none_is_comparison_ignores_custom_eq() -> None:
    """``is None`` is not affected by ``__eq__`` overloading; ``== None`` is.

    This proves why E711 matters: a custom object with a broken or
    domain-specific ``__eq__`` can make ``x == None`` return True even when
    ``x is not None``.
    """

    class AlwaysEqualToNone:
        __hash__ = None  # type: ignore[assignment]  # unhashable by design

        def __eq__(self, other: object) -> bool:
            return other is None  # broken: equals None but is not None

    obj = AlwaysEqualToNone()
    assert obj == None, "Custom __eq__ makes == None return True"  # noqa: E711
    assert obj is not None, "But is not None correctly identifies the object"


def test_falsy_non_none_values_are_not_none() -> None:
    """Falsy values (0, '', [], {}) are not None; both checks must agree."""
    for falsy in (0, "", [], {}, 0.0, False):
        assert falsy is not None, f"{falsy!r} is falsy but is not None"
        assert falsy != None, f"{falsy!r} is falsy but != None must hold"  # noqa: E711
