"""Tests for VerbosityResolver."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.core.verbosity import VerbosityLevel, VerbosityResolver


def _msg(uid: int = 42) -> SimpleNamespace:
    return SimpleNamespace(from_user=SimpleNamespace(id=uid))


class TestVerbosityLevel(unittest.TestCase):
    def test_enum_values(self) -> None:
        assert VerbosityLevel.READER.value == "reader"
        assert VerbosityLevel.DEBUG.value == "debug"


class TestVerbosityResolver(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_to_reader_when_user_missing(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(return_value=None)
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.READER

    async def test_returns_debug_when_preference_set(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": {"verbosity": "debug"}}
        )
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.DEBUG

    async def test_returns_reader_when_preference_set(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": {"verbosity": "reader"}}
        )
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.READER

    async def test_cache_hit(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": {"verbosity": "debug"}}
        )
        resolver = VerbosityResolver(repo)
        await resolver.get_verbosity(_msg(1))
        await resolver.get_verbosity(_msg(1))
        # DB should only be hit once
        assert repo.async_get_user_by_telegram_id.call_count == 1

    async def test_invalidate_cache(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": {"verbosity": "debug"}}
        )
        resolver = VerbosityResolver(repo)
        await resolver.get_verbosity(_msg(1))
        resolver.invalidate_cache(1)
        await resolver.get_verbosity(_msg(1))
        assert repo.async_get_user_by_telegram_id.call_count == 2

    async def test_fallback_on_db_error(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(side_effect=RuntimeError("db down"))
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.READER

    async def test_fallback_on_invalid_value(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": {"verbosity": "invalid"}}
        )
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.READER

    async def test_no_from_user(self) -> None:
        """Message without from_user returns READER."""
        repo = AsyncMock()
        resolver = VerbosityResolver(repo)
        msg = SimpleNamespace()  # no from_user
        level = await resolver.get_verbosity(msg)
        assert level == VerbosityLevel.READER
        repo.async_get_user_by_telegram_id.assert_not_called()

    async def test_preferences_json_not_dict(self) -> None:
        repo = AsyncMock()
        repo.async_get_user_by_telegram_id = AsyncMock(
            return_value={"preferences_json": "not-a-dict"}
        )
        resolver = VerbosityResolver(repo)
        level = await resolver.get_verbosity(_msg())
        assert level == VerbosityLevel.READER
