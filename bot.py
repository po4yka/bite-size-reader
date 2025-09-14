from __future__ import annotations

import asyncio
import logging

from app.adapters.telegram_bot import TelegramBot
from app.config import load_config
from app.db.database import Database


async def main() -> None:
    cfg = load_config()
    db = Database(cfg.runtime.db_path)
    db.migrate()

    bot = TelegramBot(cfg=cfg, db=db)
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        logging.getLogger(__name__).info("shutdown")
