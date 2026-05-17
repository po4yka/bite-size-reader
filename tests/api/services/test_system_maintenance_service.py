from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.exceptions import ProcessingError
from app.api.services.system_maintenance_service import SystemMaintenanceService


def _make_service(tmp_path, *, side_effect=None):
    database = MagicMock()

    if side_effect is not None:
        database.create_backup_copy.side_effect = side_effect
    else:

        def create_backup(dest: str) -> Path:
            path = Path(dest)
            path.write_bytes(b"pgdump-content")
            return path

        database.create_backup_copy.side_effect = create_backup

    return SystemMaintenanceService(database=database, backup_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# build_db_dump_file
# ---------------------------------------------------------------------------


def test_build_db_dump_file_returns_existing_file(tmp_path) -> None:
    service = _make_service(tmp_path)
    dump = service.build_db_dump_file(user_id=1)
    assert Path(dump.path).exists()
    assert dump.filename.startswith("ratatoskr_backup_")
    assert dump.filename.endswith(".dump")


def test_build_db_dump_file_generates_unique_path_per_request(tmp_path) -> None:
    """Each call must produce a distinct file; no shared mutable path."""
    service = _make_service(tmp_path)
    dump1 = service.build_db_dump_file(user_id=1)
    dump2 = service.build_db_dump_file(user_id=1)
    assert dump1.path != dump2.path
    assert Path(dump1.path).exists()
    assert Path(dump2.path).exists()


def test_build_db_dump_file_sets_owner_only_permissions(tmp_path) -> None:
    service = _make_service(tmp_path)
    dump = service.build_db_dump_file(user_id=1)
    mode = oct(Path(dump.path).stat().st_mode)[-3:]
    assert mode == "600"


def test_build_db_dump_file_path_is_not_predictable(tmp_path) -> None:
    """Path must not be a fixed well-known filename."""
    service = _make_service(tmp_path)
    dump = service.build_db_dump_file(user_id=1)
    assert Path(dump.path).name != "ratatoskr_backup.dump"


def test_build_db_dump_file_cleans_up_placeholder_on_backup_failure(tmp_path) -> None:
    service = _make_service(tmp_path, side_effect=RuntimeError("pg_dump failed"))

    with pytest.raises(ProcessingError):
        service.build_db_dump_file(user_id=1)

    # No stray ratatoskr_dump_* files should remain
    leftover = list(tmp_path.glob("ratatoskr_dump_*"))
    assert leftover == []


def test_build_db_dump_file_concurrent_calls_do_not_collide(tmp_path) -> None:
    """Simulate two concurrent calls; each gets its own file."""
    service = _make_service(tmp_path)
    dumps = [service.build_db_dump_file(user_id=i) for i in range(5)]
    paths = [d.path for d in dumps]
    assert len(set(paths)) == 5, "All dump paths must be unique"


# ---------------------------------------------------------------------------
# get_db_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_info_returns_allowlisted_counts() -> None:
    inspection = SimpleNamespace(
        async_get_database_overview=AsyncMock(
            return_value={"tables": {"users": 1, "unexpected_table": 1}}
        ),
        async_database_size_mb=AsyncMock(return_value=12.3),
    )
    service = SystemMaintenanceService(database=SimpleNamespace(inspection=inspection))  # type: ignore[arg-type]

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
    service = SystemMaintenanceService(database=SimpleNamespace(inspection=inspection))  # type: ignore[arg-type]

    info = await service.get_db_info()

    table_counts = cast("dict[str, int]", info["table_counts"])
    assert table_counts["__error__"] == -1


# ---------------------------------------------------------------------------
# clear_url_cache
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _create_backup
# ---------------------------------------------------------------------------


def test_create_backup_raises_processing_error_when_backup_and_cleanup_fail(tmp_path) -> None:
    database = MagicMock()
    database.create_backup_copy.side_effect = RuntimeError("backup failed")
    service = SystemMaintenanceService(
        database=database,
        backup_dir=str(tmp_path),
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
