from __future__ import annotations

import asyncio
import logging

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
    db.migrate()

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
