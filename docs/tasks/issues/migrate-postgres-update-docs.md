---
title: Update docs after Postgres cutover
status: backlog
area: docs
priority: medium
owner: Nikita Pochaev
blocks: []
blocked_by:
  - migrate-postgres-remove-peewee
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Update docs after Postgres cutover #repo/ratatoskr #area/docs #status/backlog 🔼

## Objective

Reflect the Postgres + SQLAlchemy 2.0 steady state in canonical documentation
once Peewee has been removed (L1 done).

## Context

Documents that mention SQLite or Peewee and need updating:

- `CLAUDE.md` — Tech Stack (`SQLite (Peewee ORM)`, `peewee` mentions),
  Directory Structure (`db/ (SQLite + Peewee models)`, "Peewee ORM models"),
  Quick Reference Environment Variables (`DB_PATH` deprecated; `DATABASE_URL`
  required), Debugging Tips ("SQLite at `DB_PATH`"), Best Practices, and the
  `.cursor/rules/*` fragments echoed into the project memory bundle.
- `docs/SPEC.md` — Data model section, Operations section, healthcheck
  description, all references to "Peewee".
- `README.md` — Tech stack ("Peewee ORM", "SQLite"), quickstart paragraphs.
- `docs/explanation/architecture-overview.md` — component diagram,
  persistence-layer description.
- `docs/reference/environment-variables.md` — `DATABASE_URL` documented;
  `DB_PATH` removed (no longer read).

## Acceptance criteria

- [ ] All four primary docs (`CLAUDE.md`, `docs/SPEC.md`, `README.md`,
      `docs/explanation/architecture-overview.md`) name PostgreSQL +
      SQLAlchemy 2.0 as the storage stack; "Peewee" and "SQLite" appear only
      in historical context (changelog, migration log) or in the Telethon
      session-DB carve-out.
- [ ] `docs/reference/environment-variables.md` documents `DATABASE_URL` with
      the exact DSN shape and the redacted form for `.env.example`. `DB_PATH`
      is removed.
- [ ] Architecture diagram regenerated (or the ASCII version in
      `architecture-overview.md` updated) showing Postgres + SQLAlchemy.
- [ ] `.cursor/rules/python_service.mdc` and
      `.cursor/rules/project_structure.mdc` lines that name SQLite or Peewee
      specifically are updated.
- [ ] `docs/tasks/migrate-sqlite-to-postgresql-plan.md` annotated with a
      "completed" header, final timings, and a link to the cutover log.
- [ ] All `migrate-postgres-*.md` issue files deleted from
      `docs/tasks/issues/` per the task-board lifecycle (git history is the
      audit trail).

## Notes

Sequence: this task lands **after** L1 (peewee removed). If anything in the
docs accidentally references the migrator or the legacy snapshot path, it
should be removed in the same PR.
