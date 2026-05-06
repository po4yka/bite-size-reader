from __future__ import annotations

import pytest

from app.cli._legacy_peewee_models import database_proxy

try:
    from app.db.session import DatabaseSessionManager  # type: ignore[attr-defined]
except ImportError:
    DatabaseSessionManager = None  # type: ignore[assignment,misc]


@pytest.fixture
def mcp_test_db(tmp_path):
    old_proxy_obj = database_proxy.obj
    db_path = tmp_path / "mcp.db"
    database = DatabaseSessionManager(str(db_path))
    database.migrate()
    database_proxy.initialize(database._database)
    yield database
    database._database.close()
    database_proxy.initialize(old_proxy_obj)
