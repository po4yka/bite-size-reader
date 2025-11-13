from __future__ import annotations

import asyncio
import logging

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import load_config
from app.db.database import Database

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
    db = Database(cfg.runtime.db_path)
    db.migrate()

    bot = TelegramBot(cfg=cfg, db=db)
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        logging.getLogger(__name__).info("shutdown")
