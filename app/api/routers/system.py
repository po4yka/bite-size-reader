"""System maintenance endpoints."""

import os
import tempfile
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from starlette.responses import FileResponse

from app.api.exceptions import ProcessingError, ResourceNotFoundError
from app.api.routers.auth import get_current_user
from app.config import Config
from app.core.logging_utils import get_logger
from app.db.database import Database

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

            _db = Database(path=db_path)
            _db._database.execute_sql(f"VACUUM INTO '{temp_backup_path}'")

            os.replace(temp_backup_path, backup_path)
            logger.info(f"Created database backup at {backup_path} for user {user['user_id']}")
        except Exception as e:
            logger.error(f"Database backup failed: {e}", exc_info=True)

            if os.path.exists(temp_backup_path):
                try:
                    os.remove(temp_backup_path)
                except OSError:
                    pass

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

    Uses VACUUM INTO to create a safe backup without locking the live database.
    Supports interrupted downloads via Range header (handled by FileResponse).
    """
    return _build_db_dump_response(request, user)


@router.head("/db-dump")
async def head_database(request: Request, user=Depends(get_current_user)):
    """HEAD variant for clients that only need headers/ETag before downloading."""
    return _build_db_dump_response(request, user)
