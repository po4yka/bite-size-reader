"""One-time interactive session initializer for the digest userbot.

Run manually to authenticate with phone + OTP and create the .session file:
    python -m app.cli.init_userbot_session
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _init_session() -> None:
    from pyrogram import Client

    from app.config import load_config

    cfg = load_config(allow_stub_telegram=False)

    session_dir = Path("/data")
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / cfg.digest.session_name

    logger.info("Initializing userbot session at: %s", session_path)
    logger.info("You will be prompted for phone number and OTP code.")

    client = Client(
        name=str(session_path),
        api_id=cfg.telegram.api_id,
        api_hash=cfg.telegram.api_hash,
    )

    async with client:
        me = await client.get_me()
        logger.info("Session created for user: %s (ID: %d)", me.first_name, me.id)


def main() -> int:
    try:
        asyncio.run(_init_session())
        logger.info("Session file created successfully.")
        return 0
    except KeyboardInterrupt:
        logger.info("Aborted by user.")
        return 1
    except Exception:
        logger.exception("Failed to initialize session")
        return 1


if __name__ == "__main__":
    sys.exit(main())
