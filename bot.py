from __future__ import annotations

import asyncio
import logging

from app.adapters.telegram.telegram_bot import TelegramBot
from app.config import ConfigHolder, ConfigReloader, load_config
from app.db.write_queue import DbWriteQueue
from app.di.database import build_runtime_database
from app.di.scheduler import build_scheduler_dependencies

# Use uvloop for better async performance if available
try:
    import uvloop

    uvloop.install()
except ImportError:  # pragma: no cover
    uvloop = None


async def main() -> None:
    cfg = load_config()
    cfg_holder = ConfigHolder(cfg)
    config_reloader = ConfigReloader(cfg_holder)

    # Log active model configuration at startup
    _log = logging.getLogger(__name__)
    _log.info(
        "models_config_active",
        extra={
            "openrouter_primary": cfg.openrouter.model,
            "openrouter_fallbacks": list(cfg.openrouter.fallback_models),
            "openrouter_flash": cfg.openrouter.flash_model,
            "openrouter_flash_fallbacks": list(cfg.openrouter.flash_fallback_models),
            "routing_enabled": cfg.model_routing.enabled,
            "routing_default": cfg.model_routing.default_model,
            "routing_technical": cfg.model_routing.technical_model,
            "routing_sociopolitical": cfg.model_routing.sociopolitical_model,
            "routing_long_context": cfg.model_routing.long_context_model,
            "vision_model": cfg.attachment.vision_model,
        },
    )

    # Warn if DB path is not under /data when likely running in Docker (non-persistent)
    if not cfg.runtime.db_path.startswith("/data/"):
        logging.getLogger(__name__).warning(
            "db_path_not_in_data_volume", extra={"db_path": cfg.runtime.db_path}
        )
    db = build_runtime_database(cfg, migrate=True, self_heal=True)

    db_write_queue = DbWriteQueue(maxsize=256)
    db_write_queue.start()

    # Create bot using factory pattern (while maintaining backward compatibility)
    # The factory is used internally by TelegramBot.__post_init__
    bot = TelegramBot(
        cfg=cfg_holder,  # type: ignore[arg-type]
        db=db,
        db_write_queue=db_write_queue,
        scheduler_dependencies=build_scheduler_dependencies(cfg, db),
    )
    config_reloader.start()
    try:
        await bot.start()
    finally:
        await config_reloader.stop()
        await db_write_queue.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        logging.getLogger(__name__).info("shutdown")
