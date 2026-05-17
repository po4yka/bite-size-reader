---
title: Type BackgroundProcessor repo factories against application ports
status: backlog
area: api
priority: low
owner: unassigned
blocks: []
blocked_by:
  - extract-repositories-router-into-service
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Type BackgroundProcessor repo factories against application ports #repo/ratatoskr #area/api #status/backlog 🔽

## Objective

`BackgroundProcessor` accepts repo factories typed as
`Callable[[Database], Any]`; nothing constrains the return type to
the application ports. Easy quality upgrade once the rest of the
codebase exposes typed `app/application/ports/*` for the
repositories these factories produce.

## Context

- Constructor / setters: `app/api/background_processor.py:63-77,
  154-161` — `request_repo_factory: Callable[[Database], Any] |
  None`, `summary_repo_factory: Callable[[Database], Any] | None`.

## Scope

- Replace `Any` with the concrete protocol types from
  `app/application/ports/` (e.g. `RequestRepositoryPort`,
  `SummaryRepositoryPort`).
- Add typed factory aliases in `app/application/ports/` if they
  don't exist.
- Update call sites and DI wiring as needed.

## Acceptance criteria

- [ ] No `Any` in the factory type signatures of
  `BackgroundProcessor`.
- [ ] mypy passes without `# type: ignore`.

## References

- File: `app/api/background_processor.py:63-77, 154-161`
- Ports: `app/application/ports/`
- Blocked by: [[extract-repositories-router-into-service]] (the
  service refactor will likely introduce / formalize the relevant
  ports)
