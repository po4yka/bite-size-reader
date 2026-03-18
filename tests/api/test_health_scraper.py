from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routers.auth.tokens import create_access_token
from app.db.models import User


def _auth_headers() -> dict[str, str]:
    # Use an ID from the default test ALLOWED_USER_IDS set in tests/conftest.py
    user = User.get_or_none(User.telegram_user_id == 123456789)
    if user is None:
        user = User.create(telegram_user_id=123456789, username="health_test_user")
    token = create_access_token(
        user_id=user.telegram_user_id, username=user.username, client_id="test"
    )
    return {"Authorization": f"Bearer {token}"}


def test_health_detailed_includes_scraper_component(client: TestClient) -> None:
    response = client.get("/health/detailed", headers=_auth_headers())
    assert response.status_code == 200

    payload = response.json()["data"]
    components = payload["components"]

    assert "scraper" in components
    scraper = components["scraper"]
    assert "status" in scraper
    assert "provider_order_effective" in scraper or "error" in scraper


def test_health_detailed_reuses_cached_database_details(client: TestClient, monkeypatch) -> None:
    from app.api.routers import health

    class _Cursor:
        def __init__(self, row: tuple[int, ...]) -> None:
            self._row = row

        def fetchone(self) -> tuple[int, ...]:
            return self._row

    class _Database:
        def __init__(self) -> None:
            self.select_calls = 0
            self.size_calls = 0

        def execute_sql(self, sql: str) -> _Cursor:
            if sql == "SELECT 1":
                self.select_calls += 1
                return _Cursor((1,))
            self.size_calls += 1
            return _Cursor((4096,))

    class _SessionManager:
        def __init__(self) -> None:
            self.database = _Database()
            self.integrity_calls = 0

        def check_integrity(self) -> tuple[bool, str]:
            self.integrity_calls += 1
            return True, "ok"

    session_manager = _SessionManager()

    health.clear_health_check_cache()
    monkeypatch.setattr(health, "get_session_manager", lambda: session_manager)
    monkeypatch.setattr(
        health,
        "_check_redis",
        AsyncMock(return_value={"status": "disabled", "latency_ms": 0}),
    )
    monkeypatch.setattr(
        health,
        "_check_scraper",
        AsyncMock(return_value={"status": "healthy", "latency_ms": 0}),
    )

    headers = _auth_headers()
    response_one = client.get("/health/detailed", headers=headers)
    response_two = client.get("/health/detailed", headers=headers)

    assert response_one.status_code == 200
    assert response_two.status_code == 200
    assert session_manager.database.select_calls == 2
    assert session_manager.database.size_calls == 1
    assert session_manager.integrity_calls == 1
