"""System maintenance endpoints."""

import os
import tempfile
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import FileResponse

from app.api.routers.auth import get_current_user
from app.config import Config
from app.core.logging_utils import get_logger
from app.db.database import Database

logger = get_logger(__name__)

router = APIRouter()


@router.api_route("/db-dump", methods=["GET", "HEAD"])
async def download_database(request: Request, user=Depends(get_current_user)):
    """

    Download a consistent snapshot of the SQLite database.



    Uses VACUUM INTO to create a safe backup without locking the live database.

    Supports interrupted downloads via Range header (handled by FileResponse).

    Supports HEAD requests for size checking.

    """

    # Security check: Ideally restrict to admin/owner

    # For now, we'll allow authenticated users as it's a personal app context

    db_path = Config.get("DB_PATH", "/data/app.db")

    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found")

    # Use a stable path for the backup to support resuming and caching

    backup_dir = tempfile.gettempdir()

    backup_filename = "bite_size_reader_backup.sqlite"

    backup_path = os.path.join(backup_dir, backup_filename)

    # Determine if we should regenerate the backup

    should_regenerate = True

    # 1. If resuming (Range header) or conditional request, try to use existing

    if (
        "range" in request.headers
        or "if-match" in request.headers
        or "if-unmodified-since" in request.headers
    ):
        should_regenerate = False

    # 2. Optimization: If file is fresh (< 60s), reuse it to allow HEAD -> GET consistency

    if os.path.exists(backup_path):
        try:
            mtime = os.path.getmtime(backup_path)

            if time.time() - mtime < 60:
                should_regenerate = False

        except OSError:
            # File might have vanished or be inaccessible

            should_regenerate = True

    # 3. If file missing, must regenerate

    if not os.path.exists(backup_path):
        should_regenerate = True

    if should_regenerate:
        # Generate to a temp file first, then atomic rename to handle concurrency/open files

        temp_backup_path = backup_path + ".tmp"

        try:
            if os.path.exists(temp_backup_path):
                os.remove(temp_backup_path)

            # Create a consistent snapshot using SQLite's VACUUM INTO

            _db = Database(path=db_path)

            _db._database.execute_sql(f"VACUUM INTO '{temp_backup_path}'")

            # Atomic replace

            os.replace(temp_backup_path, backup_path)

            logger.info(f"Created database backup at {backup_path} for user {user['user_id']}")

        except Exception as e:
            logger.error(f"Database backup failed: {e}", exc_info=True)

            if os.path.exists(temp_backup_path):
                try:
                    os.remove(temp_backup_path)

                except OSError:
                    pass

            raise HTTPException(
                status_code=500,
                detail=f"Backup failed: {e!s}",
            ) from e

    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found after generation")

    # Generate filename for download based on file modification time

    mtime = os.path.getmtime(backup_path)

    timestamp = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y%m%d_%H%M%S")

    download_filename = f"bite_size_reader_backup_{timestamp}.sqlite"

    # Return the file as a stream

    # FileResponse handles Range, ETag, and Last-Modified headers automatically

    return FileResponse(
        path=backup_path,
        filename=download_filename,
        media_type="application/x-sqlite3",
        # We do NOT delete the file here, as we cache it for resuming
    )
