# DEPRECATED — Legacy Migration Scripts

These scripts are superseded by **Alembic**, which is the authoritative schema migration system for Ratatoskr.

## Authoritative migration command

```bash
alembic upgrade head
# or equivalently:
python -m app.cli.migrate_db
```

Alembic revisions live in `app/db/alembic/versions/`.

## Status of this directory

- All 15 hand-written scripts (`001_` through `015_`) and `migration_runner.py` are kept for **historical reference only**.
- **Do not run any script from this directory against any database** — Alembic manages the schema exclusively.
- Do not delete files from this directory — git history is the audit trail.
