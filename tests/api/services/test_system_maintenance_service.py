from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.exceptions import ProcessingError, ResourceNotFoundError
from app.api.services.system_maintenance_service import SystemMaintenanceService


def test_build_db_dump_file_creates_backup_and_reuses_for_range_requests(tmp_path) -> None:
    database = MagicMock()

    def create_backup(dest: str) -> Path:
        path = Path(dest)
        path.write_bytes(b"dump")
        return path

    database.create_backup_copy.side_effect = create_backup
    service = SystemMaintenanceService(
        database=database,
        backup_dir=str(tmp_path),
        backup_filename="service-backup.dump",
    )

    dump_file = service.build_db_dump_file(request_headers={}, user_id=1)
    assert Path(dump_file.path).exists()
    assert dump_file.filename.startswith("ratatoskr_backup_")
    assert dump_file.filename.endswith(".dump")

    with patch.object(service, "_create_backup") as create_backup:
        reused = service.build_db_dump_file(request_headers={"Range": "bytes=0-9"}, user_id=1)

    create_backup.assert_not_called()
    assert reused.path == dump_file.path


def test_build_db_dump_file_raises_when_database_missing(tmp_path) -> None:
    database = MagicMock()
    service = SystemMaintenanceService(
        database=database,
        backup_dir=str(tmp_path),
    )

    with pytest.raises(ResourceNotFoundError):
        service.build_db_dump_file(request_headers={"Range": "bytes=0-9"}, user_id=1)


@pytest.mark.asyncio
async def test_get_db_info_returns_allowlisted_counts() -> None:
    inspection = SimpleNamespace(
        async_get_database_overview=AsyncMock(
            return_value={"tables": {"users": 1, "unexpected_table": 1}}
        ),
        async_database_size_mb=AsyncMock(return_value=12.3),
    )
    service = SystemMaintenanceService(database=SimpleNamespace(inspection=inspection))

    info = await service.get_db_info()
    file_size_mb = cast("float", info["file_size_mb"])
    table_counts = cast("dict[str, int]", info["table_counts"])

    assert file_size_mb == 12.3
    assert table_counts["users"] == 1
    assert "unexpected_table" not in table_counts


@pytest.mark.asyncio
async def test_get_db_info_handles_database_failures() -> None:
    inspection = SimpleNamespace(
        async_get_database_overview=AsyncMock(side_effect=RuntimeError("boom")),
        async_database_size_mb=AsyncMock(return_value=0.0),
    )
    service = SystemMaintenanceService(database=SimpleNamespace(inspection=inspection))

    info = await service.get_db_info()

    table_counts = cast("dict[str, int]", info["table_counts"])
    assert table_counts["__error__"] == -1


@pytest.mark.asyncio
async def test_clear_url_cache_success_and_failure() -> None:
    service = SystemMaintenanceService(database=MagicMock())
    fake_cfg = SimpleNamespace(redis=SimpleNamespace(prefix="test"))
    cache = MagicMock()
    cache.clear_prefix = AsyncMock(return_value=5)

    with (
        patch("app.api.services.system_maintenance_service.load_config", return_value=fake_cfg),
        patch("app.api.services.system_maintenance_service.RedisCache", return_value=cache),
    ):
        cleared = await service.clear_url_cache()

    assert cleared == 5
    cache.clear_prefix.assert_awaited_once_with("url")

    failing_cache = MagicMock()
    failing_cache.clear_prefix = AsyncMock(side_effect=RuntimeError("redis down"))
    with (
        patch("app.api.services.system_maintenance_service.load_config", return_value=fake_cfg),
        patch(
            "app.api.services.system_maintenance_service.RedisCache",
            return_value=failing_cache,
        ),
    ):
        with pytest.raises(ProcessingError, match="Cache clear failed"):
            await service.clear_url_cache()


def test_create_backup_raises_processing_error_when_backup_and_cleanup_fail(tmp_path) -> None:
    database = MagicMock()
    database.create_backup_copy.side_effect = RuntimeError("backup failed")
    service = SystemMaintenanceService(
        database=database,
        backup_dir=str(tmp_path),
        backup_filename="broken.dump",
    )
    backup_path = os.path.join(str(tmp_path), "broken.dump")

    with (
        patch(
            "app.api.services.system_maintenance_service.os.path.exists",
            side_effect=[False, True],
        ),
        patch(
            "app.api.services.system_maintenance_service.os.remove",
            side_effect=OSError("cleanup failed"),
        ),
    ):
        with pytest.raises(ProcessingError, match="temporary file cleanup also failed"):
            service._create_backup(backup_path=backup_path, user_id=1)
