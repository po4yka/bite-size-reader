"""System maintenance endpoints."""

import os
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import FileResponse

from app.api.routers.auth import get_current_user
from app.config import Config
from app.core.logging_utils import get_logger
from app.db.database import Database

logger = get_logger(__name__)
router = APIRouter()


@router.get("/db-dump")
async def download_database(user=Depends(get_current_user)):
    """
    Download a consistent snapshot of the SQLite database.

    Uses VACUUM INTO to create a safe backup without locking the live database.
    Supports interrupted downloads via Range header (handled by FileResponse).
    """
    # Security check: Ideally restrict to admin/owner
    # For now, we'll allow authenticated users as it's a personal app context

    db_path = Config.get("DB_PATH", "/data/app.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Database file not found")

    # Create a temporary file for the backup
    # We use a temp directory that persists for the request duration
    # In a real heavy-load scenario, we might want to cache this or manage cleanup differently
    backup_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"bite_size_reader_backup_{timestamp}.sqlite"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        # Create a consistent snapshot using SQLite's VACUUM INTO
        # This works even if the DB is in WAL mode and being written to
        _db = Database(path=db_path)
        _db._database.execute_sql(f"VACUUM INTO '{backup_path}'")

        logger.info(f"Created database backup at {backup_path} for user {user['user_id']}")

        # Return the file as a stream
        # FileResponse handles Range headers automatically for resume support
        return FileResponse(
            path=backup_path,
            filename=backup_filename,
            media_type="application/x-sqlite3",
            background=None,  # We rely on OS/temp dir cleanup or need a background task to delete after some time
        )

        # Note: Cleaning up the file *immediately* after response is tricky with FileResponse
        # because it streams. A BackgroundTask can delete it, but if we want to support
        # range requests/resuming later, we might need to keep it for a bit.
        # For this simple implementation, we'll leave it in temp (OS cleans up eventually)
        # or we could implement a more complex token-based download system.

    except Exception as e:
        logger.error(f"Database backup failed: {e}", exc_info=True)
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass
        raise HTTPException(
            status_code=500,
            detail=f"Backup failed: {e!s}",
        ) from e
