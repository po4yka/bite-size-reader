"""Database migration runner with version tracking.

This module provides a migration framework for managing database schema changes:
- Tracks applied migrations in a dedicated table
- Runs migrations in order by filename
- Supports rollback of individual migrations
- Provides safety checks and transaction support

Usage:
    from app.cli.migrations.migration_runner import MigrationRunner
    from app.db.database import Database

    db = Database("/data/app.db")
    runner = MigrationRunner(db)

    # Run all pending migrations
    count = runner.run_pending()
    print(f"Applied {count} migrations")

    # Rollback a specific migration
    runner.rollback("001_add_performance_indexes")
"""

from __future__ import annotations

import datetime as dt
import importlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import peewee

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


class MigrationHistory(peewee.Model):
    """Track applied migrations in the database."""

    migration_name = peewee.TextField(primary_key=True)
    applied_at = peewee.DateTimeField(default=dt.datetime.utcnow)
    rollback_sql = peewee.TextField(null=True)  # Optional rollback instructions

    class Meta:
        table_name = "migration_history"


class MigrationError(Exception):
    """Raised when a migration fails."""


class MigrationRunner:
    """Manages database schema migrations with version tracking."""

    def __init__(self, db: DatabaseSessionManager | Any):
        """Initialize migration runner.

        Args:
            db: DatabaseSessionManager or Database instance to run migrations against
        """
        self.db = db
        self._ensure_migration_table()

    def _ensure_migration_table(self) -> None:
        """Create migration history table if it doesn't exist."""
        # Handle both DatabaseSessionManager (db.database) and legacy Database (db._database)
        db_instance = getattr(self.db, "database", getattr(self.db, "_database", None))
        if db_instance is None:
            msg = "Provided db object does not have a database instance"
            raise TypeError(msg)

        # Bind MigrationHistory to the database proxy
        MigrationHistory._meta.database = db_instance

        # Create table outside of transaction to ensure it persists
        db_instance.create_tables([MigrationHistory], safe=True)
        logger.debug("Migration history table ensured")

    def get_applied_migrations(self) -> set[str]:
        """Get set of applied migration names.

        Returns:
            Set of migration names that have been applied
        """
        return {m.migration_name for m in MigrationHistory.select()}

    def get_pending_migrations(self) -> list[Path]:
        """Get list of pending migration files in order.

        Returns:
            List of migration file paths, sorted by filename
        """
        migrations_dir = Path(__file__).parent
        all_migrations = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.py"))

        applied = self.get_applied_migrations()

        pending = [m for m in all_migrations if m.stem not in applied]

        logger.debug(
            f"Found {len(all_migrations)} total migrations, "
            f"{len(applied)} applied, {len(pending)} pending"
        )

        return pending

    def validate_migration_file(self, migration_path: Path) -> tuple[bool, str]:
        """Validate that a migration file has required structure.

        Args:
            migration_path: Path to migration file

        Returns:
            Tuple of (is_valid, error_message)
        """
        migration_name = migration_path.stem

        try:
            # Import migration module
            module_name = f"app.cli.migrations.{migration_name}"
            module = importlib.import_module(module_name)

            # Check for required functions
            if not hasattr(module, "upgrade"):
                return False, "Missing upgrade() function"

            if not hasattr(module, "downgrade"):
                return False, "Missing downgrade() function"

            # Verify function signatures
            upgrade_fn = module.upgrade
            if not callable(upgrade_fn):
                return False, "upgrade is not callable"

            return True, ""

        except ImportError as e:
            return False, f"Failed to import migration: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    def run_migration(self, migration_path: Path, dry_run: bool = False) -> None:
        """Run a single migration file.

        Args:
            migration_path: Path to migration file
            dry_run: If True, don't actually run the migration, just validate

        Raises:
            MigrationError: If migration fails validation or execution
        """
        migration_name = migration_path.stem

        # Validate migration file
        is_valid, error_msg = self.validate_migration_file(migration_path)
        if not is_valid:
            raise MigrationError(f"Migration {migration_name} failed validation: {error_msg}")

        if dry_run:
            logger.info(f"[DRY RUN] Would run migration: {migration_name}")
            return

        logger.info(f"Running migration: {migration_name}")

        # Import migration module
        module_name = f"app.cli.migrations.{migration_name}"
        module = importlib.import_module(module_name)

        # Get upgrade function
        upgrade_fn: Callable[[DatabaseSessionManager], None] = module.upgrade

        # Run migration in transaction
        db_instance = getattr(self.db, "database", getattr(self.db, "_database", None))
        try:
            with db_instance.atomic():
                # Execute upgrade
                upgrade_fn(self.db)

                # Record migration in history
                MigrationHistory.create(
                    migration_name=migration_name,
                    applied_at=dt.datetime.utcnow(),
                )

                logger.info(f"✓ Migration {migration_name} completed successfully")

        except Exception as e:
            logger.error(f"✗ Migration {migration_name} failed")
            raise MigrationError(f"Migration {migration_name} failed: {e}") from e

    def run_pending(self, dry_run: bool = False) -> int:
        """Run all pending migrations in order.

        Args:
            dry_run: If True, don't actually run migrations, just validate

        Returns:
            Number of migrations applied (or would be applied in dry run)

        Raises:
            MigrationError: If any migration fails
        """
        pending = self.get_pending_migrations()

        if not pending:
            logger.info("No pending migrations")
            return 0

        logger.info(
            f"Found {len(pending)} pending migration(s): {', '.join(p.stem for p in pending)}"
        )

        if dry_run:
            logger.info("[DRY RUN] Would apply the following migrations:")
            for migration_path in pending:
                logger.info(f"  - {migration_path.stem}")
            return len(pending)

        for migration_path in pending:
            self.run_migration(migration_path, dry_run=dry_run)

        logger.info(f"Successfully applied {len(pending)} migration(s)")
        return len(pending)

    def rollback(self, migration_name: str) -> None:
        """Rollback a specific migration.

        Args:
            migration_name: Name of migration to rollback (without .py extension)

        Raises:
            MigrationError: If rollback fails or migration not found
        """
        # Check if migration was applied
        with self.db.database.connection_context():
            history = MigrationHistory.get_or_none(
                MigrationHistory.migration_name == migration_name
            )

            if not history:
                raise MigrationError(f"Migration {migration_name} has not been applied")

        logger.info(f"Rolling back migration: {migration_name}")

        migrations_dir = Path(__file__).parent
        migration_path = migrations_dir / f"{migration_name}.py"

        if not migration_path.exists():
            raise MigrationError(f"Migration file not found: {migration_path}")

        # Import migration module
        module_name = f"app.cli.migrations.{migration_name}"
        module = importlib.import_module(module_name)

        # Get downgrade function
        downgrade_fn: Callable[[DatabaseSessionManager], None] = module.downgrade

        # Run rollback in transaction
        db_instance = getattr(self.db, "database", getattr(self.db, "_database", None))
        try:
            with db_instance.atomic():
                # Execute downgrade
                downgrade_fn(self.db)

                # Remove from history
                MigrationHistory.delete().where(
                    MigrationHistory.migration_name == migration_name
                ).execute()

                logger.info(f"✓ Migration {migration_name} rolled back successfully")

        except Exception as e:
            logger.exception(f"✗ Rollback of {migration_name} failed")
            raise MigrationError(f"Rollback of {migration_name} failed: {e}") from e

    def get_migration_status(self) -> dict[str, Any]:
        """Get status of all migrations.

        Returns:
            Dictionary with migration status information
        """
        migrations_dir = Path(__file__).parent
        all_migrations = sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.py"))

        applied = self.get_applied_migrations()

        status: dict[str, Any] = {
            "total": len(all_migrations),
            "applied": len(applied),
            "pending": len(all_migrations) - len(applied),
            "migrations": [],
        }

        for migration_path in all_migrations:
            name = migration_path.stem
            is_applied = name in applied

            migration_info: dict[str, Any] = {
                "name": name,
                "applied": is_applied,
            }

            if is_applied:
                with self.db.database.connection_context():
                    history = MigrationHistory.get(MigrationHistory.migration_name == name)
                    migration_info["applied_at"] = history.applied_at.isoformat()

            status["migrations"].append(migration_info)

        return status


def main() -> int:
    """CLI entry point for migration runner."""
    import sys

    from app.db.session import DatabaseSessionManager

    if len(sys.argv) < 2:
        print("Usage: python -m app.cli.migrations.migration_runner <command> [args]")
        print("\nCommands:")
        print("  status               - Show migration status")
        print("  pending              - List pending migrations")
        print("  run [--dry-run]      - Run pending migrations")
        print("  rollback <name>      - Rollback a specific migration")
        return 1

    command = sys.argv[1]
    db_path = "/data/app.db"

    # Allow specifying database path with --db flag
    if "--db" in sys.argv:
        db_index = sys.argv.index("--db")
        if len(sys.argv) > db_index + 1:
            db_path = sys.argv[db_index + 1]

    logger.info(f"Using database: {db_path}")

    db = DatabaseSessionManager(path=db_path)
    runner = MigrationRunner(db)

    try:
        if command == "status":
            status = runner.get_migration_status()
            print("\nMigration Status:")
            print(f"  Total: {status['total']}")
            print(f"  Applied: {status['applied']}")
            print(f"  Pending: {status['pending']}")
            print("\nMigrations:")
            for m in status["migrations"]:
                status_icon = "✓" if m["applied"] else "○"
                applied_at = f" (applied {m['applied_at']})" if m["applied"] else ""
                print(f"  {status_icon} {m['name']}{applied_at}")
            return 0

        if command == "pending":
            pending = runner.get_pending_migrations()
            if not pending:
                print("No pending migrations")
            else:
                print(f"Pending migrations ({len(pending)}):")
                for p in pending:
                    print(f"  - {p.stem}")
            return 0

        if command == "run":
            dry_run = "--dry-run" in sys.argv
            count = runner.run_pending(dry_run=dry_run)
            if dry_run:
                print(f"[DRY RUN] Would apply {count} migration(s)")
            else:
                print(f"Applied {count} migration(s)")
            return 0

        if command == "rollback":
            if len(sys.argv) < 3:
                print("Error: rollback requires migration name")
                return 1
            migration_name = sys.argv[2]
            runner.rollback(migration_name)
            print(f"Rolled back migration: {migration_name}")
            return 0

        print(f"Unknown command: {command}")
        return 1

    except MigrationError as e:
        logger.error(f"Migration error: {e}")
        return 1
    except Exception:
        logger.exception("Unexpected error")
        return 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    sys.exit(main())
