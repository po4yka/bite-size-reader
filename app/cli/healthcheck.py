"""Container healthcheck for the configured PostgreSQL database."""

from __future__ import annotations

import asyncio
import os
import sys

from app.config import DatabaseConfig
from app.db.session import Database


async def _run_healthcheck() -> None:
    # `DatabaseConfig` is a plain `BaseModel`, not `BaseSettings`, so the
    # `validation_alias="DATABASE_URL"` field is only consulted during
    # `model_validate(mapping)` — bare `DatabaseConfig()` does not read
    # env vars. Pass `DATABASE_URL` through explicitly so the compose
    # healthcheck command works whether or not `POSTGRES_PASSWORD` is
    # also set.
    dsn = os.environ.get("DATABASE_URL", "").strip()
    config = (
        DatabaseConfig.model_validate({"DATABASE_URL": dsn}) if dsn else DatabaseConfig()
    )
    database = Database(config=config)
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
