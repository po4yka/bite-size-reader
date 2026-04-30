"""Preflight checker for the Telethon digest userbot session."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.adapters.telegram.telethon_compat import TelethonUserClient
from app.core.logging_utils import get_logger

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = get_logger(__name__)


async def _check_session() -> int:
    from app.config import load_config

    cfg = load_config(allow_stub_telegram=False)
    session_path = Path("/data") / cfg.digest.session_name
    session_file = session_path.with_suffix(".session")
    if not session_file.exists():
        logger.error("Telethon userbot session file not found: %s", session_file)
        return 2

    client = TelethonUserClient(
        session_path=str(session_path),
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
    )
    await client.start()
    try:
        me = await client.get_me()
        logger.info("Telethon userbot session ready: %s (%s)", me.first_name, me.id)
        return 0
    finally:
        await client.disconnect()


def main() -> int:
    try:
        return asyncio.run(_check_session())
    except KeyboardInterrupt:
        logger.info("Aborted by user.")
        return 1
    except Exception:
        logger.exception("Telethon userbot session check failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
