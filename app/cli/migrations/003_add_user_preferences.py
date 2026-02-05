"""Add preferences_json field to User table.

This migration adds a JSON field to store user preferences including:
- Language preference (en/ru/auto)
- Notification settings (enabled, frequency)
- App settings (theme, font size)

The field is nullable and defaults to None, so existing users won't be affected.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import peewee
from playhouse.migrate import SqliteMigrator, migrate

from app.core.logging_utils import log_exception

if TYPE_CHECKING:
    from app.db.database import Database
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def upgrade(db: Database | DatabaseSessionManager) -> None:
    """Add preferences_json field to users table."""
    migrator = SqliteMigrator(db._database)

    try:
        # Add preferences_json column (nullable JSON field)
        with db._database.atomic():
            migrate(
                migrator.add_column(
                    "users",
                    "preferences_json",
                    peewee.TextField(null=True),
                )
            )

        logger.info("Added preferences_json column to users table")

    except peewee.OperationalError as e:
        # Column might already exist
        if "duplicate column name" in str(e).lower():
            logger.info("preferences_json column already exists, skipping")
        else:
            raise


def downgrade(db: Database | DatabaseSessionManager) -> None:
    """Remove preferences_json field from users table."""
    migrator = SqliteMigrator(db._database)

    try:
        with db._database.atomic():
            migrate(migrator.drop_column("users", "preferences_json"))

        logger.info("Removed preferences_json column from users table")

    except peewee.OperationalError as e:
        log_exception(logger, "preferences_column_drop_failed", e, level="warning")
