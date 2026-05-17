"""Tests for the encapsulated `_current_runtime` holder in app/di/api.py.

Per [[eliminate-module-globals]], `_current_runtime` was the
single most dangerous module-level global in the API DI layer
because it leaked between test processes via three `global
_current_runtime` declarations. This test pins the post-refactor
behaviour: the public functions still work, but the `global`
keyword is gone from `app/di/api.py`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.di import api as di_api


@pytest.fixture(autouse=True)
def _isolate_runtime() -> object:
    di_api.clear_current_api_runtime()
    yield
    di_api.clear_current_api_runtime()


class TestPublicFunctionsStillWork:
    def test_set_then_get_returns_runtime(self) -> None:
        fake = MagicMock(name="ApiRuntime")
        di_api.set_current_api_runtime(fake)
        assert di_api.get_current_api_runtime() is fake

    def test_get_without_set_raises(self) -> None:
        with pytest.raises(RuntimeError):
            di_api.get_current_api_runtime()

    def test_clear_resets(self) -> None:
        fake = MagicMock(name="ApiRuntime")
        di_api.set_current_api_runtime(fake)
        di_api.clear_current_api_runtime()
        with pytest.raises(RuntimeError):
            di_api.get_current_api_runtime()

    def test_set_twice_replaces(self) -> None:
        fake_a = MagicMock(name="ApiRuntime")
        fake_b = MagicMock(name="ApiRuntime")
        di_api.set_current_api_runtime(fake_a)
        di_api.set_current_api_runtime(fake_b)
        assert di_api.get_current_api_runtime() is fake_b


class TestGlobalKeywordEliminated:
    def test_no_global_keyword_remains(self) -> None:
        src = Path(di_api.__file__).read_text(encoding="utf-8")
        # The three legacy `global _current_runtime` declarations must
        # be gone. Single-element holder pattern eliminates the need.
        assert "global _current_runtime" not in src
