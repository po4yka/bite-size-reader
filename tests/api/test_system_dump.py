import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.routers.auth.tokens import create_access_token
from app.db.models import User


def test_db_dump_head_and_get(client: TestClient, db):
    # Setup auth - Create user in DB with owner permissions (required for db-dump)
    user = User.create(telegram_user_id=123456789, username="test_dump_user", is_owner=True)

    token = create_access_token(user.telegram_user_id, client_id="test_client")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test HEAD
    response_head = client.head("/v1/system/db-dump", headers=headers)

    assert response_head.status_code == 200, f"HEAD failed: {response_head.text}"
    assert "content-length" in response_head.headers
    assert response_head.headers["accept-ranges"] == "bytes"
    etag = response_head.headers.get("etag")
    assert etag

    # 2. Test GET
    response_get = client.get("/v1/system/db-dump", headers=headers)
    assert response_get.status_code == 200
    assert response_get.headers["etag"] == etag

    # 3. Test Resume (Range)
    # Request first 10 bytes
    headers_range = headers.copy()
    headers_range["Range"] = "bytes=0-9"
    response_range = client.get("/v1/system/db-dump", headers=headers_range)

    assert response_range.status_code == 206
    assert len(response_range.content) == 10
    assert response_range.headers["content-range"].startswith("bytes 0-9/")
    assert response_range.headers["etag"] == etag  # Should match the original


def test_db_dump_regeneration_logic(client: TestClient, db):
    # Setup auth - Create user in DB with owner permissions (use different ID to avoid conflict)
    try:
        user = User.get(telegram_user_id=987654321)
    except Exception:
        user = User.create(telegram_user_id=987654321, username="test_dump_user_2", is_owner=True)

    token = create_access_token(user.telegram_user_id, client_id="test")
    headers = {"Authorization": f"Bearer {token}"}

    # First request to generate the file
    response1 = client.get("/v1/system/db-dump", headers=headers)
    assert response1.status_code == 200
    etag1 = response1.headers["etag"]

    # Immediate second request (should reuse)
    response2 = client.get("/v1/system/db-dump", headers=headers)
    assert response2.status_code == 200
    assert response2.headers["etag"] == etag1

    # Manually modify the backup file's mtime to be old (e.g. 70 seconds ago)
    # to force regeneration
    import tempfile

    backup_path = os.path.join(tempfile.gettempdir(), "ratatoskr_backup.sqlite")

    if os.path.exists(backup_path):
        old_time = time.time() - 70
        os.utime(backup_path, (old_time, old_time))

    # Third request (should regenerate and get new ETag)
    response3 = client.get("/v1/system/db-dump", headers=headers)
    assert response3.status_code == 200
    assert response3.headers["etag"] != etag1


def test_db_info_requires_owner(client: TestClient, db):
    owner = User.create(telegram_user_id=111111111, username="owner_user", is_owner=True)
    non_owner = User.create(telegram_user_id=222222222, username="normal_user", is_owner=False)

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
    owner = User.create(telegram_user_id=555555555, username="owner_user3", is_owner=True)
    owner_token = create_access_token(owner.telegram_user_id, client_id="test")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    db._database.execute_sql("CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)")
    db._database.execute_sql("INSERT INTO unexpected_table (id) VALUES (1)")

    with patch("app.api.routers.auth.dependencies.Config.get_allowed_user_ids", return_value=[]):
        response = client.get("/v1/system/db-info", headers=owner_headers)

    assert response.status_code == 200
    table_counts = response.json().get("data", {}).get("table_counts", {})
    assert "unexpected_table" not in table_counts
    assert "requests" in table_counts


def test_clear_cache_requires_owner(client: TestClient, db):
    owner = User.create(telegram_user_id=333333333, username="owner_user2", is_owner=True)
    non_owner = User.create(telegram_user_id=444444444, username="normal_user2", is_owner=False)

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
