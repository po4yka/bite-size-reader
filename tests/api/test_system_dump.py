from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routers.auth.tokens import create_access_token
from app.db.models import User


# ---------------------------------------------------------------------------
# db-dump endpoint
# ---------------------------------------------------------------------------


def test_db_dump_get_returns_file(client: TestClient, db):
    user = User.create(telegram_user_id=123456789, username="test_dump_user", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/v1/system/db-dump", headers=headers)

    assert response.status_code == 200
    assert "content-length" in response.headers
    assert len(response.content) > 0


def test_db_dump_head_returns_headers(client: TestClient, db):
    user = User.create(telegram_user_id=123456780, username="test_dump_head", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.head("/v1/system/db-dump", headers=headers)

    assert response.status_code == 200
    assert "content-length" in response.headers
    assert response.headers["accept-ranges"] == "bytes"


def test_db_dump_range_request_returns_partial_content(client: TestClient, db):
    user = User.create(telegram_user_id=123456781, username="test_dump_range", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}", "Range": "bytes=0-9"}

    response = client.get("/v1/system/db-dump", headers=headers)

    assert response.status_code == 206
    assert len(response.content) == 10
    assert response.headers["content-range"].startswith("bytes 0-9/")


def test_db_dump_file_is_cleaned_up_after_response(client: TestClient, db):
    """Temp dump file must be deleted once the response is fully sent."""
    user = User.create(telegram_user_id=123456782, username="test_dump_cleanup", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    created_paths: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def capturing_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_paths.append(path)
        return fd, path

    with patch(
        "app.api.services.system_maintenance_service.tempfile.mkstemp",
        side_effect=capturing_mkstemp,
    ):
        response = client.get("/v1/system/db-dump", headers=headers)

    assert response.status_code == 200
    assert len(created_paths) == 1
    assert not Path(created_paths[0]).exists(), "Dump file was not deleted after response"


def test_db_dump_uses_unique_path_per_request(client: TestClient, db):
    """Two consecutive requests must not share the same temp file."""
    user = User.create(telegram_user_id=123456783, username="test_dump_unique", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    created_paths: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def capturing_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_paths.append(path)
        return fd, path

    with patch(
        "app.api.services.system_maintenance_service.tempfile.mkstemp",
        side_effect=capturing_mkstemp,
    ):
        client.get("/v1/system/db-dump", headers=headers)
        client.get("/v1/system/db-dump", headers=headers)

    assert len(created_paths) == 2
    assert created_paths[0] != created_paths[1], "Both requests must use distinct temp paths"


def test_db_dump_requires_owner(client: TestClient, db):
    non_owner = User.create(telegram_user_id=222222222, username="normal_user_dump", is_owner=False)  # type: ignore[attr-defined]
    token = create_access_token(non_owner.telegram_user_id, client_id="test")
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        response = client.get("/v1/system/db-dump", headers=headers)

    assert response.status_code == 403


def test_db_dump_path_is_not_fixed_predictable_name(client: TestClient, db):
    """Generated file must not be the old hardcoded ratatoskr_backup.dump."""
    user = User.create(telegram_user_id=123456784, username="test_dump_name", is_owner=True)  # type: ignore[attr-defined]
    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    created_paths: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def capturing_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_paths.append(path)
        return fd, path

    with patch(
        "app.api.services.system_maintenance_service.tempfile.mkstemp",
        side_effect=capturing_mkstemp,
    ):
        client.get("/v1/system/db-dump", headers=headers)

    assert created_paths
    assert os.path.basename(created_paths[0]) != "ratatoskr_backup.dump"


# ---------------------------------------------------------------------------
# db-info endpoint
# ---------------------------------------------------------------------------


def test_db_info_requires_owner(client: TestClient, db):
    owner = User.create(telegram_user_id=111111111, username="owner_user", is_owner=True)  # type: ignore[attr-defined]
    non_owner = User.create(telegram_user_id=222222223, username="normal_user", is_owner=False)  # type: ignore[attr-defined]

    owner_token = create_access_token(owner.telegram_user_id, client_id="test")
    non_owner_token = create_access_token(non_owner.telegram_user_id, client_id="test")

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    non_owner_headers = {"Authorization": f"Bearer {non_owner_token}"}

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        forbidden_resp = client.get("/v1/system/db-info", headers=non_owner_headers)
        assert forbidden_resp.status_code == 403

        ok_resp = client.get("/v1/system/db-info", headers=owner_headers)
        assert ok_resp.status_code == 200
    data = ok_resp.json().get("data", {})
    assert "file_size_mb" in data
    assert "table_counts" in data


def test_db_info_skips_unallowlisted_tables(client: TestClient, db):
    owner = User.create(telegram_user_id=555555555, username="owner_user3", is_owner=True)  # type: ignore[attr-defined]
    owner_token = create_access_token(owner.telegram_user_id, client_id="test")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        response = client.get("/v1/system/db-info", headers=owner_headers)

    assert response.status_code == 200
    table_counts = response.json().get("data", {}).get("table_counts", {})
    assert "unexpected_table" not in table_counts
    assert "requests" in table_counts


# ---------------------------------------------------------------------------
# clear-cache endpoint
# ---------------------------------------------------------------------------


def test_clear_cache_requires_owner(client: TestClient, db):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    owner = User.create(telegram_user_id=333333333, username="owner_user2", is_owner=True)  # type: ignore[attr-defined]
    non_owner = User.create(telegram_user_id=444444444, username="normal_user2", is_owner=False)  # type: ignore[attr-defined]

    owner_token = create_access_token(owner.telegram_user_id, client_id="test")
    non_owner_token = create_access_token(non_owner.telegram_user_id, client_id="test")

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    non_owner_headers = {"Authorization": f"Bearer {non_owner_token}"}

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        forbidden_resp = client.post("/v1/system/clear-cache", headers=non_owner_headers)
        assert forbidden_resp.status_code == 403

    fake_cfg = SimpleNamespace(redis=SimpleNamespace(prefix="test"))
    with (
        patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]),
        patch("app.config.settings.load_config", return_value=fake_cfg),
        patch("app.infrastructure.redis.get_redis", new=AsyncMock(return_value=None)),
    ):
        ok_resp = client.post("/v1/system/clear-cache", headers=owner_headers)
    assert ok_resp.status_code == 200
    assert ok_resp.json().get("data", {}).get("cleared_keys") == 0
