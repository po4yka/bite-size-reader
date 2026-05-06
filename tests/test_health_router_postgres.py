from __future__ import annotations

import pytest

from app.api.routers import health


class _Inspection:
    def __init__(self) -> None:
        self.size_calls = 0
        self.integrity_calls = 0

    async def async_database_size_mb(self) -> float:
        self.size_calls += 1
        return 4.0

    async def async_check_integrity(self) -> tuple[bool, str]:
        self.integrity_calls += 1
        return True, "ok"


class _Database:
    def __init__(self) -> None:
        self.healthcheck_calls = 0
        self.inspection = _Inspection()

    async def healthcheck(self) -> None:
        self.healthcheck_calls += 1


@pytest.mark.asyncio
async def test_check_database_uses_async_postgres_runtime_and_caches_details(monkeypatch) -> None:
    database = _Database()

    health.clear_health_check_cache()
    monkeypatch.setattr(health, "get_session_manager", lambda: database)

    first = await health._check_database(include_details=True)
    second = await health._check_database(include_details=True)

    assert first["status"] == "healthy"
    assert first["size_mb"] == 4.0
    assert first["integrity_ok"] is True
    assert second["status"] == "healthy"
    assert database.healthcheck_calls == 2
    assert database.inspection.size_calls == 1
    assert database.inspection.integrity_calls == 1
