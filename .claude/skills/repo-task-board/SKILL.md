---
name: repo-task-board
description: Use when creating, updating, triaging, or completing repository tasks stored as Obsidian Tasks Markdown lines with #task, #status/*, #repo/ratatoskr, and #area/* tags. Use for docs/tasks/*.md, Kanban board maintenance, backlog grooming, and agent-ready implementation planning.
---

# Repository Task Board — ratatoskr

This repository uses Obsidian Tasks-compatible Markdown checkboxes as the canonical task system.

## Canonical task line

```md
- [ ] #task <imperative task title> #repo/ratatoskr #area/<area> #status/<status> <priority> [paperclip:POY-N]
```

## Allowed statuses

- `#status/backlog`
- `#status/todo`
- `#status/doing`
- `#status/review`
- `#status/blocked`
- `#status/done`
- `#status/dropped`

## Priority markers

- `🔺` critical  ·  `⏫` high  ·  `🔼` medium  ·  `🔽` low

## Canonical files

- `docs/tasks/backlog.md` — `#status/backlog` items by area
- `docs/tasks/active.md` — `#status/todo`, `#status/doing`, `#status/review`
- `docs/tasks/blocked.md` — `#status/blocked` items with reason
- `docs/tasks/dashboard.md` — Obsidian Tasks query hub
- `docs/ROADMAP_PRIORITIES.md` — cross-project roadmap (strategic, not per-task)

## Rules

1. Preserve valid Obsidian Tasks syntax.
2. Never create duplicate task lines for the same work.
3. Prefer editing the existing task line over adding a new one.
4. Keep task titles imperative and implementation-oriented.
5. Exactly one `#status/*` tag per task; remove the previous one when transitioning.
6. Add `#blocked` alongside `#status/blocked`; add an indented reason below.
7. When completing: change `[ ]` to `[x]`, set `#status/done`, add `✅ YYYY-MM-DD`.
8. `docs/ROADMAP_PRIORITIES.md` is a strategic planning document — task details go in `docs/tasks/`.
9. Preserve `[paperclip:POY-N]` cross-reference tokens on existing tasks.
10. Do not change unrelated prose, code, or other sections.

## Task creation workflow

1. Search `docs/tasks/` for similar tasks.
2. If similar task exists, update it instead of duplicating.
3. Choose the right file: `backlog.md` for new work, `active.md` if starting now.
4. Assign: `#repo/ratatoskr`, `#area/<area>`, one `#status/*`, priority marker.
5. Add context as indented bullets only when acceptance criteria is non-obvious.
