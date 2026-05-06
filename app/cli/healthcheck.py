"""Container healthcheck for the configured PostgreSQL database."""

from __future__ import annotations

import asyncio
import sys

from app.config import DatabaseConfig
from app.db.session import Database


async def _run_healthcheck() -> None:
    database = Database(config=DatabaseConfig())
    try:
        await database.healthcheck()
    finally:
        await database.dispose()


def main() -> int:
    try:
        asyncio.run(_run_healthcheck())
    except Exception as exc:
        print(f"database healthcheck failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
