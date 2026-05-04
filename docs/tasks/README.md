# Task Board — ratatoskr

This folder is the Obsidian vault for ratatoskr task management.

## Structure

| File / Folder | Purpose |
|---|---|
| `active.md` | Live Obsidian Tasks query — doing + review |
| `backlog.md` | Live Obsidian Tasks query — backlog |
| `blocked.md` | Live Obsidian Tasks query — blocked |
| `dashboard.md` | Full query hub — all statuses + Bases links |
| `board.md` | Kanban board — visual swim-lane view |
| `issues/POY-NNN.md` | One file per task — source of truth |
| `templates/new-task.md` | Templater template for new tasks |
| `views/*.base` | Obsidian Bases structured views |

## Canonical task line

Each `issues/POY-NNN.md` file contains exactly one `- [ ]` line:

```md
- [ ] #task <title> #repo/ratatoskr #area/<area> #status/<status> <priority> [[POY-NNN]]
```

## Allowed statuses

`#status/backlog` · `#status/todo` · `#status/doing` · `#status/review` · `#status/blocked` · `#status/done` · `#status/dropped`

## Priority markers

`🔺` critical · `⏫` high · `🔼` medium · `🔽` low

## YAML frontmatter schema

```yaml
---
id: POY-NNN
title: Imperative task title
status: doing          # backlog | todo | doing | review | blocked | done | dropped
area: auth             # auth | api | kmp | sync | ci | frontend | observability | testing | content | scraper | llm | db | docs | ops
priority: high         # critical | high | medium | low
owner: Role name
paperclip: POY-NNN
blocks: []             # list of POY-NNN IDs this task blocks
blocked_by: []         # list of POY-NNN IDs blocking this task
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

## Lifecycle

1. **New task** — run Templater: "Create new note from template" → `new-task.md`. Fill prompts. File lands in `issues/`.
2. **Status transition** — update `status:` in frontmatter AND change the `#status/*` tag in the canonical `- [ ]` line. Move the file to the right Obsidian Tasks query view automatically.
3. **Done** — delete `issues/POY-NNN.md`. Git history is the audit trail: `git log -- docs/tasks/issues/POY-NNN.md`.

## Open in Obsidian

Open the **repo root** (`/path/to/ratatoskr`) as your Obsidian vault — not this subfolder. The root `.obsidian/` contains the Tasks plugin config with global filter `#task`.
