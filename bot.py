from __future__ import annotations

import asyncio
import logging
import sqlite3

import peewee

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import load_config
from app.db.session import DatabaseSessionManager
from app.db.write_queue import DbWriteQueue

# Use uvloop for better async performance if available
try:
    import uvloop

    uvloop.install()
except ImportError:  # pragma: no cover
    pass


_log = logging.getLogger(__name__)


def _migrate_with_self_heal(db: DatabaseSessionManager) -> None:
    """Run db.migrate() with self-healing on index corruption.

    On OperationalError, runs PRAGMA integrity_check to diagnose the issue.
    If corruption is detected, executes REINDEX and retries migration once.
    """
    try:
        db.migrate()
    except (peewee.OperationalError, sqlite3.OperationalError) as first_err:
        _log.warning(
            "db_migrate_failed",
            extra={"error": str(first_err), "error_type": type(first_err).__name__},
        )

        # Diagnose with integrity_check
        try:
            with db.connect() as conn:
                cursor = conn.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                integrity_result = result[0] if result else "unknown"
        except Exception as diag_err:
            _log.error(
                "db_integrity_check_failed",
                extra={"error": str(diag_err)},
            )
            raise first_err from diag_err

        _log.warning(
            "db_integrity_check_result",
            extra={"result": integrity_result},
        )

        if integrity_result != "ok":
            # Attempt REINDEX to repair corrupt indexes
            _log.warning("db_reindex_starting")
            try:
                with db.connect() as conn:
                    conn.execute("REINDEX")
                _log.info("db_reindex_completed")
            except Exception as reindex_err:
                _log.critical(
                    "db_reindex_failed",
                    extra={"error": str(reindex_err)},
                )
                raise first_err from reindex_err

        # Retry migration once after REINDEX (or if integrity was ok but migrate failed)
        try:
            db.migrate()
            _log.info("db_migrate_retry_succeeded")
        except (peewee.OperationalError, sqlite3.OperationalError) as retry_err:
            _log.critical(
                "db_migrate_retry_failed",
                extra={"error": str(retry_err), "error_type": type(retry_err).__name__},
            )
            raise


async def main() -> None:
    cfg = load_config()
    # Warn if DB path is not under /data when likely running in Docker (non-persistent)
    if not cfg.runtime.db_path.startswith("/data/"):
        logging.getLogger(__name__).warning(
            "db_path_not_in_data_volume", extra={"db_path": cfg.runtime.db_path}
        )
    db = DatabaseSessionManager(
        path=cfg.runtime.db_path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )
    _migrate_with_self_heal(db)

    db_write_queue = DbWriteQueue(maxsize=256)
    db_write_queue.start()

    # Create bot using factory pattern (while maintaining backward compatibility)
    # The factory is used internally by TelegramBot.__post_init__
    bot = TelegramBot(cfg=cfg, db=db, db_write_queue=db_write_queue)
    try:
        await bot.start()
    finally:
        await db_write_queue.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        logging.getLogger(__name__).info("shutdown")
