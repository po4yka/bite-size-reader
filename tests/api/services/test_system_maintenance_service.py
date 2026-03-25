from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.exceptions import ProcessingError, ResourceNotFoundError
from app.application.services.system_maintenance_service import SystemMaintenanceService
from app.db.models import User


def test_build_db_dump_file_creates_backup_and_reuses_for_range_requests(db, tmp_path) -> None:
    User.create(telegram_user_id=7001, username="system-user")
    service = SystemMaintenanceService(
        db_path=str(db._database.database),
        backup_dir=str(tmp_path),
        backup_filename="service-backup.sqlite",
    )

    dump_file = service.build_db_dump_file(request_headers={}, user_id=1)
    assert Path(dump_file.path).exists()
    assert dump_file.filename.startswith("bite_size_reader_backup_")

    with patch.object(service, "_create_backup") as create_backup:
        reused = service.build_db_dump_file(request_headers={"Range": "bytes=0-9"}, user_id=1)

    create_backup.assert_not_called()
    assert reused.path == dump_file.path


def test_build_db_dump_file_raises_when_database_missing(tmp_path) -> None:
    service = SystemMaintenanceService(
        db_path=str(tmp_path / "missing.sqlite"),
        backup_dir=str(tmp_path),
    )

    with pytest.raises(ResourceNotFoundError):
        service.build_db_dump_file(request_headers={}, user_id=1)


def test_get_db_info_returns_allowlisted_counts(db) -> None:
    User.create(telegram_user_id=7002, username="db-info-user")
    db._database.execute_sql("CREATE TABLE unexpected_table (id INTEGER PRIMARY KEY)")
    db._database.execute_sql("INSERT INTO unexpected_table (id) VALUES (1)")
    service = SystemMaintenanceService(db_path=str(db._database.database))

    info = service.get_db_info()
    file_size_mb = cast("float", info["file_size_mb"])
    table_counts = cast("dict[str, int]", info["table_counts"])

    assert file_size_mb >= 0
    assert "users" in table_counts
    assert "unexpected_table" not in table_counts


def test_get_db_info_handles_sqlite_failures(tmp_path) -> None:
    service = SystemMaintenanceService(db_path=str(tmp_path / "broken.sqlite"))

    with patch(
        "app.application.services.system_maintenance_service.sqlite3.connect",
        side_effect=sqlite3.Error("boom"),
    ):
        info = service.get_db_info()

    table_counts = cast("dict[str, int]", info["table_counts"])
    assert table_counts["__error__"] == -1


@pytest.mark.asyncio
async def test_clear_url_cache_success_and_failure() -> None:
    service = SystemMaintenanceService(db_path="/tmp/unused.sqlite")
    fake_cfg = SimpleNamespace(redis=SimpleNamespace(prefix="test"))
    cache = MagicMock()
    cache.clear_prefix = AsyncMock(return_value=5)

    with (
        patch(
            "app.application.services.system_maintenance_service.load_config", return_value=fake_cfg
        ),
        patch("app.application.services.system_maintenance_service.RedisCache", return_value=cache),
    ):
        cleared = await service.clear_url_cache()

    assert cleared == 5
    cache.clear_prefix.assert_awaited_once_with("url")

    failing_cache = MagicMock()
    failing_cache.clear_prefix = AsyncMock(side_effect=RuntimeError("redis down"))
    with (
        patch(
            "app.application.services.system_maintenance_service.load_config", return_value=fake_cfg
        ),
        patch(
            "app.application.services.system_maintenance_service.RedisCache",
            return_value=failing_cache,
        ),
    ):
        with pytest.raises(ProcessingError, match="Cache clear failed"):
            await service.clear_url_cache()


def test_create_backup_raises_processing_error_when_backup_and_cleanup_fail(tmp_path) -> None:
    db_path = tmp_path / "app.sqlite"
    db_path.write_text("placeholder")
    service = SystemMaintenanceService(
        db_path=str(db_path),
        backup_dir=str(tmp_path),
        backup_filename="broken.sqlite",
    )
    backup_path = os.path.join(str(tmp_path), "broken.sqlite")

    with (
        patch(
            "app.application.services.system_maintenance_service.sqlite3.connect",
            side_effect=sqlite3.Error("backup failed"),
        ),
        patch(
            "app.application.services.system_maintenance_service.os.path.exists",
            side_effect=[False, True],
        ),
        patch(
            "app.application.services.system_maintenance_service.os.remove",
            side_effect=OSError("cleanup failed"),
        ),
    ):
        with pytest.raises(ProcessingError, match="temporary file cleanup also failed"):
            service._create_backup(backup_path=backup_path, user_id=1)
