"""Programmatic Alembic runner for the PostgreSQL schema."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from alembic.config import Config

logger = get_logger(__name__)

_INI_PATH = str(Path(__file__).resolve().parents[2] / "alembic.ini")


def _resolve_dsn(dsn: str | None) -> str:
    resolved = (dsn or os.getenv("DATABASE_URL", "")).strip()
    if not resolved:
        password = os.getenv("POSTGRES_PASSWORD", "").strip()
        if password:
            resolved = f"postgresql+asyncpg://ratatoskr_app:{password}@postgres:5432/ratatoskr"
    return resolved


def _build_alembic_config(dsn: str | None = None) -> Config:
    """Build Alembic config with the PostgreSQL asyncpg URL."""
    from alembic.config import Config

    resolved_dsn = _resolve_dsn(dsn)
    if not resolved_dsn.startswith("postgresql+asyncpg://"):
        msg = "Alembic requires a postgresql+asyncpg:// URL"
        raise RuntimeError(msg)

    cfg = Config(_INI_PATH)
    cfg.set_main_option("sqlalchemy.url", resolved_dsn)
    return cfg


def upgrade_to_head(dsn: str | None = None) -> None:
    """Run pending Alembic revisions to head."""
    from alembic import command

    cfg = _build_alembic_config(dsn)
    command.upgrade(cfg, "head")
    logger.info("alembic_upgrade_complete")


def print_status(dsn: str | None = None) -> None:
    """Print current Alembic revision and migration history to stdout."""
    from alembic import command

    cfg = _build_alembic_config(dsn)
    print("Current revision:")
    command.current(cfg, verbose=True)
    print("\nMigration history:")
    command.history(cfg, verbose=False)
