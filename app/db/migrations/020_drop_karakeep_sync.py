"""Drop karakeep_sync table."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)


def upgrade(db: DatabaseSessionManager) -> None:
    """Drop the karakeep_sync table."""
    db._database.execute_sql("DROP TABLE IF EXISTS karakeep_sync")
    logger.info("migration_020_complete")


def downgrade(db: DatabaseSessionManager) -> None:
    """Table cannot be restored (data loss)."""
