"""Database bootstrap and migration services."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.db.models import ALL_MODELS, database_proxy

if TYPE_CHECKING:
    import peewee
from app.db.schema_migrator import SchemaMigrator
from app.db.topic_search_index import TopicSearchIndexManager


class DatabaseBootstrapService:
    """Own database initialization, migrations, and startup index work."""

    def __init__(
        self,
        *,
        path: str,
        database: peewee.SqliteDatabase,
        logger: Any,
    ) -> None:
        self._path = path
        self._database = database
        self._logger = logger
        self._topic_search = TopicSearchIndexManager(self._database, self._logger)

    def initialize_database_proxy(self) -> None:
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        database_proxy.initialize(self._database)

    def migrate(self) -> None:
        with self._database.connection_context(), self._database.bind_ctx(ALL_MODELS):
            self._database.create_tables(ALL_MODELS, safe=True)

            from app.cli.migrations.migration_runner import MigrationRunner

            runner = MigrationRunner(self)
            runner.run_pending()
            SchemaMigrator(self._database, self._logger).ensure_schema_compatibility()
            self._topic_search.ensure_index()

        self._logger.info("db_migrated", extra={"path": self._mask_path(self._path)})

    @staticmethod
    def _mask_path(path: str) -> str:
        try:
            p = Path(path)
            if not p.name:
                return str(p)
            parent = p.parent.name
            if parent:
                return f".../{parent}/{p.name}"
            return p.name
        except (OSError, ValueError, AttributeError):
            return "..."
