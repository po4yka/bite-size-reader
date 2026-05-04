"""Test configuration for tests/db/.

The root conftest sets DB_PATH (via manage_api_session_manager) to an api-session
path for API-test isolation.  Alembic's env.py reads DB_PATH first and would use
that path instead of the sqlalchemy.url set by _build_alembic_config(db_path),
causing all alembic_runner tests to operate on the wrong database file.

This local conftest clears DB_PATH so that env.py falls through to sqlalchemy.url,
which is always set explicitly by _build_alembic_config().
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_db_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent the global DB_PATH fixture from overriding Alembic's sqlalchemy.url."""
    monkeypatch.delenv("DB_PATH", raising=False)
