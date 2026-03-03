"""System maintenance endpoints."""

import os
import sqlite3
import tempfile
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from starlette.responses import FileResponse

from app.api.exceptions import ProcessingError, ResourceNotFoundError
from app.api.routers.auth import get_current_user
from app.api.services.auth_service import AuthService
from app.config import Config
from app.core.logging_utils import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _build_db_dump_response(request: Request, user: dict):
    """Create or reuse a SQLite backup and prepare a streaming response."""
    db_path = Config.get("DB_PATH", "/data/app.db")

    if not os.path.exists(db_path):
        raise ResourceNotFoundError("Database file", db_path)

    backup_dir = tempfile.gettempdir()
    backup_filename = "bite_size_reader_backup.sqlite"
    backup_path = os.path.join(backup_dir, backup_filename)

    should_regenerate = True

    if (
        "range" in request.headers
        or "if-match" in request.headers
        or "if-unmodified-since" in request.headers
    ):
        should_regenerate = False

    if os.path.exists(backup_path):
        try:
            mtime = os.path.getmtime(backup_path)
            if time.time() - mtime < 60:
                should_regenerate = False
        except OSError:
            should_regenerate = True

    if not os.path.exists(backup_path):
        should_regenerate = True

    if should_regenerate:
        temp_backup_path = backup_path + ".tmp"

        try:
            if os.path.exists(temp_backup_path):
                os.remove(temp_backup_path)

            # Use SQLite backup API instead of VACUUM INTO to avoid SQL injection
            source_conn = sqlite3.connect(db_path)
            backup_conn = sqlite3.connect(temp_backup_path)
            try:
                source_conn.backup(backup_conn)
            finally:
                backup_conn.close()
                source_conn.close()

            os.replace(temp_backup_path, backup_path)
            logger.info(f"Created database backup at {backup_path} for user {user['user_id']}")
        except Exception as e:
            logger.error(f"Database backup failed: {e}", exc_info=True)

            if os.path.exists(temp_backup_path):
                try:
                    os.remove(temp_backup_path)
                except OSError as cleanup_exc:
                    logger.debug("temp_backup_cleanup_failed", extra={"error": str(cleanup_exc)})

            raise ProcessingError(f"Backup failed: {e!s}") from e

    if not os.path.exists(backup_path):
        raise ResourceNotFoundError("Backup file", backup_path)

    mtime = os.path.getmtime(backup_path)
    timestamp = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y%m%d_%H%M%S")
    download_filename = f"bite_size_reader_backup_{timestamp}.sqlite"

    return FileResponse(
        path=backup_path,
        filename=download_filename,
        media_type="application/x-sqlite3",
    )


@router.get("/db-dump")
async def download_database(request: Request, user=Depends(get_current_user)):
    """
    Download a consistent snapshot of the SQLite database.

    Uses SQLite backup API to create a safe backup without locking the live database.
    Supports interrupted downloads via Range header (handled by FileResponse).

    Requires owner permissions.
    """
    await AuthService.require_owner(user)
    return _build_db_dump_response(request, user)


@router.head("/db-dump")
async def head_database(request: Request, user=Depends(get_current_user)):
    """HEAD variant for clients that only need headers/ETag before downloading.

    Requires owner permissions.
    """
    await AuthService.require_owner(user)
    return _build_db_dump_response(request, user)


@router.get("/db-info")
async def get_db_info(user=Depends(get_current_user)):
    """Get database information: table row counts and file size."""
    from app.api.models.responses import success_response

    await AuthService.require_owner(user)

    db_path = Config.get("DB_PATH", "/data/app.db")

    file_size_mb = 0.0
    if os.path.exists(db_path):
        file_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)

    table_counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        for table in sorted(tables):
            try:
                cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
                table_counts[table] = cursor.fetchone()[0]
            except Exception:
                table_counts[table] = -1
        conn.close()
    except Exception as e:
        logger.error("db_info_failed", extra={"error": str(e)})

    return success_response(
        {
            "file_size_mb": file_size_mb,
            "table_counts": table_counts,
            "db_path": db_path,
        }
    )


@router.post("/clear-cache")
async def clear_cache(user=Depends(get_current_user)):
    """Clear Redis URL cache."""
    from app.api.models.responses import success_response
    from app.config.settings import load_config
    from app.infrastructure.redis import get_redis

    await AuthService.require_owner(user)

    cfg = load_config(allow_stub_telegram=True)
    redis_client = await get_redis(cfg)

    cleared = 0
    if redis_client:
        try:
            keys: list[bytes] = []
            async for key in redis_client.scan_iter(match=f"{cfg.redis.prefix}:url:*"):
                keys.append(key)
            if keys:
                cleared = await redis_client.delete(*keys)
        except Exception as e:
            logger.error("clear_cache_failed", extra={"error": str(e)})
            raise ProcessingError(f"Cache clear failed: {e}") from e

    return success_response({"cleared_keys": cleared})
