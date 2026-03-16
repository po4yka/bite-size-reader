from __future__ import annotations

import pytest

from app.db.models import database_proxy
from app.db.session import DatabaseSessionManager


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
