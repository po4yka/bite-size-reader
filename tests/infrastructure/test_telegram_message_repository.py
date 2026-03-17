"""Tests for SqliteTelegramMessageRepositoryAdapter.

Structural/unit tests covering importability and method contracts.
Full async persistence tests require a live DB session and are covered
by integration tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.infrastructure.persistence.sqlite.repositories.telegram_message_repository import (
    SqliteTelegramMessageRepositoryAdapter,
)


def test_repository_can_be_instantiated() -> None:
    session = MagicMock()
    repo = SqliteTelegramMessageRepositoryAdapter(session)
    assert repo._session is session


def test_repository_has_expected_methods() -> None:
    session = MagicMock()
    repo = SqliteTelegramMessageRepositoryAdapter(session)
    assert callable(getattr(repo, "async_insert_telegram_message", None))
    assert callable(getattr(repo, "async_get_telegram_message_by_request", None))
