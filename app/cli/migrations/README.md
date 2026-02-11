# Database Migrations

This directory contains versioned database schema migrations for the Bite-Size Reader project.

## Quick Start

```bash
# Check migration status
python -m app.cli.migrations.migration_runner status

# List pending migrations
python -m app.cli.migrations.migration_runner pending

# Run pending migrations
python -m app.cli.migrations.migration_runner run

# Dry run (validate without applying)
python -m app.cli.migrations.migration_runner run --dry-run

# Rollback a specific migration
python -m app.cli.migrations.migration_runner rollback 001_add_performance_indexes
```

## How It Works

1. **Migration Files**: Numbered files like `001_add_performance_indexes.py`
2. **Tracking**: Applied migrations tracked in `migration_history` table
3. **Transactions**: Each migration runs in a transaction for safety
4. **Rollback**: Each migration includes a `downgrade()` function

## Creating a New Migration

1. **Create file** with next number: `002_your_migration_name.py`

2. **Add required functions**:

```python
"""Short description of what this migration does."""

from __future__ import annotations

import logging
from app.db.database import Database

logger = logging.getLogger(__name__)


def upgrade(db: Database) -> None:
    """Apply migration changes."""
    with db._database.connection_context():
        # Your migration code here
        db._database.execute_sql("""
            ALTER TABLE some_table
            ADD COLUMN new_column TEXT
        """)

    logger.info("Migration completed")


def downgrade(db: Database) -> None:
    """Revert migration changes."""
    with db._database.connection_context():
        # Your rollback code here
        # Note: SQLite doesn't support DROP COLUMN
        # You may need to recreate the table
        pass

    logger.info("Migration rolled back")
```

1. **Test migration**:

```bash
# Dry run first
python -m app.cli.migrations.migration_runner run --dry-run

# Apply migration
python -m app.cli.migrations.migration_runner run
```

## Migration Best Practices

### DO

- ✅ Use descriptive names: `001_add_user_indexes.py`
- ✅ Keep migrations small and focused
- ✅ Test rollback before committing
- ✅ Add detailed docstrings
- ✅ Log what you're doing
- ✅ Use transactions for safety
- ✅ Check if changes already exist (idempotent)

### DON'T

- ❌ Edit applied migrations (create new one instead)
- ❌ Mix schema and data changes
- ❌ Forget to test rollback
- ❌ Use string formatting in SQL (use parameterized queries)
- ❌ Assume table/column exists (check first)

## Common Migration Patterns

### Adding an Index

```python
def upgrade(db: Database) -> None:
    """Add index for faster queries."""
    with db._database.connection_context():
        # Check if index exists
        indexes = db._database.get_indexes("my_table")
        if any(idx.name == "idx_my_index" for idx in indexes):
            logger.info("Index already exists, skipping")
            return

        # Create index
        db._database.execute_sql("""
            CREATE INDEX idx_my_index
            ON my_table(column_name)
        """)

def downgrade(db: Database) -> None:
    """Remove index."""
    with db._database.connection_context():
        db._database.execute_sql("DROP INDEX IF EXISTS idx_my_index")
```

### Adding a Column

```python
def upgrade(db: Database) -> None:
    """Add new column to table."""
    with db._database.connection_context():
        # Check if column exists
        columns = db._database.get_columns("my_table")
        if any(col.name == "new_column" for col in columns):
            logger.info("Column already exists, skipping")
            return

        # Add column
        db._database.execute_sql("""
            ALTER TABLE my_table
            ADD COLUMN new_column TEXT DEFAULT NULL
        """)

def downgrade(db: Database) -> None:
    """Remove column (SQLite limitation)."""
    # SQLite doesn't support DROP COLUMN before 3.35.0
    # You need to recreate the table without the column
    logger.warning(
        "SQLite doesn't support DROP COLUMN easily. "
        "Manual rollback required or use SQLite 3.35+."
    )
```

### Data Migration

```python
def upgrade(db: Database) -> None:
    """Migrate data to new format."""
    with db._database.connection_context():
        # Fetch old format data
        rows = db._database.execute_sql("""
            SELECT id, old_column FROM my_table
            WHERE new_column IS NULL
        """).fetchall()

        # Transform and update
        for row_id, old_value in rows:
            new_value = transform(old_value)
            db._database.execute_sql("""
                UPDATE my_table
                SET new_column = ?
                WHERE id = ?
            """, (new_value, row_id))

        logger.info(f"Migrated {len(rows)} rows")
```

## SQLite Limitations

SQLite has limited ALTER TABLE support:

- ✅ Can add columns
- ✅ Can rename tables
- ✅ Can rename columns (SQLite 3.25+)
- ❌ Cannot drop columns (before 3.35)
- ❌ Cannot alter column types
- ❌ Cannot add constraints to existing columns

**Workaround**: Recreate table with new schema:

```python
def upgrade(db: Database) -> None:
    """Recreate table with new schema."""
    with db._database.connection_context():
        # Create new table with desired schema
        db._database.execute_sql("""
            CREATE TABLE my_table_new (
                id INTEGER PRIMARY KEY,
                column1 TEXT NOT NULL,
                column2 TEXT  -- changed from NULL to NOT NULL
            )
        """)

        # Copy data
        db._database.execute_sql("""
            INSERT INTO my_table_new (id, column1, column2)
            SELECT id, column1, COALESCE(column2, 'default')
            FROM my_table
        """)

        # Swap tables
        db._database.execute_sql("DROP TABLE my_table")
        db._database.execute_sql("ALTER TABLE my_table_new RENAME TO my_table")

        # Recreate indexes
        db._database.execute_sql("""
            CREATE INDEX idx_my_table_column1
            ON my_table(column1)
        """)
```

## Troubleshooting

### Migration Fails Mid-Way

Migrations run in transactions, so failures should rollback automatically:

```bash
# Check what was applied
python -m app.cli.migrations.migration_runner status

# Fix the migration file
# vim app/cli/migrations/002_broken_migration.py

# Try again
python -m app.cli.migrations.migration_runner run
```

### Need to Manually Fix

If you need to manually intervene:

```bash
# Connect to database
sqlite3 /data/app.db

# Check migration history
SELECT * FROM migration_history;

# Manually mark migration as not applied
DELETE FROM migration_history WHERE migration_name = '002_broken';

# Exit and retry
.quit
python -m app.cli.migrations.migration_runner run
```

### Migration Applied but Not in History

```bash
# Manually mark as applied
sqlite3 /data/app.db
INSERT INTO migration_history (migration_name, applied_at)
VALUES ('001_add_indexes', datetime('now'));
```

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Run database migrations
  run: |
    # Dry run first to catch errors
    python -m app.cli.migrations.migration_runner run --dry-run

    # Apply migrations
    python -m app.cli.migrations.migration_runner run

    # Verify
    python -m app.cli.migrations.migration_runner status
```

### Docker

```dockerfile
# In your Dockerfile
RUN python -m app.cli.migrations.migration_runner run
```

Or run migrations on container startup:

```bash
# In entrypoint.sh
python -m app.cli.migrations.migration_runner run
python -m bot
```

## Migration History

| Migration | Description | Date |
| ----------- | ------------- | ------ |
| `001_add_performance_indexes` | Add indexes for common queries | 2025-11-14 |

## Resources

- [Peewee Migrations](http://docs.peewee-orm.com/en/latest/peewee/playhouse.html#schema-migrations)
- [SQLite ALTER TABLE](https://www.sqlite.org/lang_altertable.html)
- [Database Migration Best Practices](https://www.brunton-spall.co.uk/post/2014/05/06/database-migrations-done-right/)
