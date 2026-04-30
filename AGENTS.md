# AGENTS.md -- AI Agent Guide for Ratatoskr

This document provides project context for AI coding agents (Codex, Copilot, etc.). For the full guide see `CLAUDE.md`.

## Project Overview

Async Telegram bot that summarizes web articles, YouTube videos, and forwarded channel posts. Returns structured JSON summaries with a strict contract. Single Docker container, owner-only access.

**Stack:** Python 3.13+, Pyrogram, Scrapling/Firecrawl/Playwright (scraper chain), OpenRouter (LLM), SQLite (Peewee ORM), FastAPI, React 18 + TypeScript + Vite (Frost web frontend).

## Architecture

```
Telegram/API -> MessageRouter -> URL/Forward Handler -> ScraperChain -> LLM -> Summary JSON -> SQLite
```

### Key Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| Telegram | `app/adapters/telegram/` | Bot orchestration, routing, commands |
| Content | `app/adapters/content/` | Scraper chain (Scrapling -> Defuddle -> Firecrawl -> Playwright -> Crawlee -> direct HTTP) |
| YouTube | `app/adapters/youtube/` | yt-dlp download, transcript extraction |
| Twitter/X | `app/adapters/twitter/` | Firecrawl + Playwright extraction |
| LLM | `app/adapters/llm/`, `app/adapters/openrouter/` | Provider-agnostic LLM interface |
| Domain | `app/domain/` | Business models and domain services |
| Application | `app/application/` | DTOs, ports, use cases, and application services |
| Infrastructure | `app/infrastructure/` | Concrete persistence, vector search, cache, and messaging adapters |
| DI | `app/di/` | Runtime composition only |
| Core | `app/core/` | URL normalization, JSON parsing, summary contract, logging |
| Database | `app/db/` | Peewee ORM models (48 classes), `DatabaseSessionManager` (`session.py`) is sole DB entry point |
| API | `app/api/` | FastAPI REST API with JWT auth |
| Web | `clients/web/` | Frost web interface (React + TypeScript + Vite) |
| Search | `app/application/services/`, `app/infrastructure/search/`, `app/infrastructure/embedding/` | Search workflows, vector search, and embedding services |
| MCP | `app/mcp/` | Model Context Protocol server |

## Critical Files

- `app/adapters/telegram/message_router.py` -- Central routing logic
- `app/adapters/content/url_processor.py` -- URL processing orchestration
- `app/core/summary_contract.py` -- Summary validation (strict contract)
- `app/core/url_utils.py` -- URL normalization and deduplication
- `app/db/models.py` -- Database schema (ORM models)
- `app/db/session.py` -- `DatabaseSessionManager` (sole DB entry point)
- `app/config/settings.py` -- Configuration loading
- `app/config/scraper.py` -- Scraper chain configuration
- `bot.py` -- Entrypoint
- `docs/SPEC.md` -- Full technical specification (canonical reference)
- `docs/reference/frontend-web.md` -- Web frontend contracts
- `DESIGN.md` -- Frost design system spec (DESIGN.md format). Canonical for web UI tokens, typography, components, and anti-patterns.

## Development Commands

```bash
source .venv/bin/activate
make format          # ruff format + isort
make lint            # ruff
make type            # mypy
cd clients/web && npm run check:static && npm run test  # Web frontend
python -m app.cli.summary --url <URL>           # CLI test runner
```

## Code Conventions

- **Formatting:** ruff format + isort (profile=black)
- **Linting:** Ruff (see `pyproject.toml`)
- **Type checking:** mypy (`python_version = "3.13"`)
- **Pre-commit hooks:** ruff -> isort -> mypy
- **Testing:** pytest + pytest-asyncio. Test DB helpers in `tests/db_helpers.py`
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)

## Key Rules

1. All URLs must be normalized before deduplication (`app/core/url_utils.py`)
2. All user-visible errors must include `Error ID: <correlation_id>`
3. Persist everything: scraper responses, LLM calls, Telegram messages
4. Always redact `Authorization` headers before logging
5. Update both `en/` and `ru/` prompts when changing LLM behavior
6. Validate summary JSON with `app/core/summary_contract.py`
7. Database changes require migration via `app/cli/migrate_db.py` + docs/SPEC.md update
8. Web frontend changes: read `docs/reference/frontend-web.md` first, run `npm run check:static` before finalizing. Web UI must adapt to ≤768px via container queries on AppShell main; see DESIGN.md Mobile section.
9. State scope explicitly when giving an instruction; don't expect silent generalization across items
10. Tell the agent what to do, not what to avoid (e.g., "use `tests/db_helpers.py`" vs. "don't write new fixtures")
11. Front-load the full task spec on the first turn; iterative refinement loses context against multi-step plans
12. Make independent tool calls in parallel; sequence only when one result determines the next call's parameters
13. Read code before asserting its behavior; cite `file:line` for non-obvious claims
14. Web UI design: read `DESIGN.md` (Frost) before adding tokens, components, colors, or motion. Use `--frost-*` tokens; do not introduce arbitrary hex values or new CSS custom properties outside the Frost token set.

## Database

48 Peewee model classes in `app/db/models.py`. `DatabaseSessionManager` (`app/db/session.py`) handles connection management, migrations, FTS5 indexing, and async operations via `AsyncRWLock`. No other DB entry point exists.

## Summary JSON Contract

Defined in `app/core/summary_contract.py` (validation) and `app/core/summary_schema.py` (Pydantic model). Core fields: `summary_250`, `summary_1000`, `tldr`, `key_ideas`, `topic_tags`, `entities`, `estimated_reading_time_min`. Full contract has 35+ fields. See `docs/SPEC.md`.

---

<!-- desloppify-begin -->
<!-- desloppify-skill-version: 2 -->
<!-- markdownlint-disable MD003 MD029 -->
---

name: desloppify
description: >
  Codebase health scanner and technical debt tracker. Use when the user asks
  about code quality, technical debt, dead code, large files, god classes,
  duplicate functions, code smells, naming issues, import cycles, or coupling
  problems. Also use when asked for a health score, what to fix next, or to
  create a cleanup plan. Supports 28 languages.
allowed-tools: Bash(desloppify *)
---

# Desloppify

## 1. Your Job

Improve code quality by maximising the **strict score** honestly.

**The main thing you do is run `desloppify next`** — it tells you exactly what to fix and how. Fix it, resolve it, run `next` again. Keep going.

Follow the scan output's **INSTRUCTIONS FOR AGENTS** — don't substitute your own analysis.

## 2. The Workflow

Two loops. The **outer loop** rescans periodically to measure progress.
The **inner loop** is where you spend most of your time: fixing issues one by one.

### Outer loop — scan and check

```bash
desloppify scan --path .       # analyse the codebase
desloppify status              # check scores — are we at target?
```

If not at target, work the inner loop. Rescan periodically — especially after clearing a cluster or batch of related fixes. Issues cascade-resolve and new ones may surface.

### Inner loop — fix issues

Repeat until the queue is clear:

```
1. desloppify next              ← tells you exactly what to fix next
2. Fix the issue in code
3. Resolve it (next shows you the exact command including required attestation)
```

Score may temporarily drop after fixes — cascade effects are normal, keep going.
If `next` suggests an auto-fixer, run `desloppify fix <fixer> --dry-run` to preview, then apply.

**To be strategic**, use `plan` to shape what `next` gives you:

```bash
desloppify plan                        # see the full ordered queue
desloppify plan move <pat> top         # reorder — what unblocks the most?
desloppify plan cluster create <name>  # group related issues to batch-fix
desloppify plan focus <cluster>        # scope next to one cluster
desloppify plan defer <pat>            # push low-value items aside
desloppify plan skip <pat>             # hide from next
desloppify plan done <pat>             # mark complete
desloppify plan reopen <pat>           # reopen
```

### Subjective reviews

The scan will prompt you when a subjective review is needed — just follow its instructions.
If you need to trigger one manually:

```bash
desloppify review --run-batches --runner codex --parallel --scan-after-import
```

### Other useful commands

```bash
desloppify next --count 5                         # top 5 priorities
desloppify next --cluster <name>                  # drill into a cluster
desloppify show <pattern>                         # filter by file/detector/ID
desloppify show --status open                     # all open findings
desloppify plan skip --permanent "<id>" --note "reason" # accept debt (lowers strict score)
desloppify scan --path . --reset-subjective       # reset subjective baseline to 0
```

## 3. Reference

### How scoring works

Overall score = **40% mechanical** + **60% subjective**.

- **Mechanical (40%)**: auto-detected issues — duplication, dead code, smells, unused imports, security. Fixed by changing code and rescanning.
- **Subjective (60%)**: design quality review — naming, error handling, abstractions, clarity. Starts at **0%** until reviewed. The scan will prompt you when a review is needed.
- **Strict score** is the north star: wontfix items count as open. The gap between overall and strict is your wontfix debt.
- **Score types**: overall (lenient), strict (wontfix counts), objective (mechanical only), verified (confirmed fixes only).

### Subjective reviews in detail

- **Preferred**: `desloppify review --run-batches --runner codex --parallel --scan-after-import` — does everything in one command.
- **Manual path**: `desloppify review --prepare` → review per dimension → `desloppify review --import file.json`.
- Import first, fix after — import creates tracked state entries for correlation.
- Integrity: reviewers score from evidence only. Scores hitting exact targets trigger auto-reset.
- Even moderate scores (60-80) dramatically improve overall health.
- Stale dimensions auto-surface in `next` — just follow the queue.

### Key concepts

- **Tiers**: T1 auto-fix → T2 quick manual → T3 judgment call → T4 major refactor.
- **Auto-clusters**: related findings are auto-grouped in `next`. Drill in with `next --cluster <name>`.
- **Zones**: production/script (scored), test/config/generated/vendor (not scored). Fix with `zone set`.
- **Wontfix cost**: widens the lenient↔strict gap. Challenge past decisions when the gap grows.
- Score can temporarily drop after fixes (cascade effects are normal).

## 4. Escalate Tool Issues Upstream

When desloppify itself appears wrong or inconsistent:

1. Capture a minimal repro (`command`, `path`, `expected`, `actual`).
2. Open a GitHub issue in `peteromallet/desloppify`.
3. If you can fix it safely, open a PR linked to that issue.
4. If unsure whether it is tool bug vs user workflow, issue first, PR second.

## Prerequisite

`command -v desloppify >/dev/null 2>&1 && echo "desloppify: installed" || echo "NOT INSTALLED — run: pip install --upgrade git+https://github.com/peteromallet/desloppify.git"`

<!-- desloppify-end -->

## Impeccable Design Skills

Curated UI/UX design skills from [impeccable](https://github.com/pbakaus/impeccable) for the Frost web frontend. Codex skills in `.codex/skills/i-*/`.

| Command | Purpose |
|---------|---------|
| `i-frontend-design` | Core design framework -- run first |
| `i-audit` | Accessibility, performance, responsive checks |
| `i-polish` | Final refinement pass |
| `i-normalize` | Align to design system tokens |
| `i-typeset` | Typography improvements |
| `i-colorize` | Strategic color usage |
| `i-clarify` | UX copy improvements |
| `i-harden` | i18n, error handling, edge cases |
| `i-optimize` | Performance (Core Web Vitals) |

## Codex Overlay

This is the canonical Codex overlay used by the README install command.

1. Prefer first-class batch runs: `desloppify review --run-batches --runner codex --parallel --scan-after-import`.
2. The command writes immutable packet snapshots under `.desloppify/review_packets/holistic_packet_*.json`; use those for reproducible retries.
3. Keep reviewer input scoped to the immutable packet and the source files named in each batch.
4. Do not use prior chat context, score history, narrative summaries, issue labels, or target-threshold anchoring while scoring.
5. Assess every dimension listed in `query.dimensions`; never drop a requested dimension. If evidence is weak/mixed, score lower and explain uncertainty in findings.
6. Return machine-readable JSON only for review imports. For Claude session submit (`--external-submit`), include `session` from the generated template:

```json
{
  "session": {
    "id": "<session_id_from_template>",
    "token": "<session_token_from_template>"
  },
  "assessments": {
    "<dimension_from_query>": 0
  },
  "findings": [
    {
      "dimension": "<dimension_from_query>",
      "identifier": "short_id",
      "summary": "one-line defect summary",
      "related_files": ["relative/path/to/file.py"],
      "evidence": ["specific code observation"],
      "suggestion": "concrete fix recommendation",
      "confidence": "high|medium|low"
    }
  ]
}
```

7. `findings` MUST match `query.system_prompt` exactly (including `related_files`, `evidence`, and `suggestion`). Use `"findings": []` when no defects are found.
8. Import is fail-closed by default: if any finding is invalid/skipped, `desloppify review --import` aborts unless `--allow-partial` is explicitly passed.
9. Assessment scores are auto-applied from trusted internal run-batches imports, or via Claude cloud session imports (`desloppify review --external-start --external-runner claude` then printed `--external-submit`). Legacy attested external import via `--attested-external` remains supported.
10. Manual override is safety-scoped: you cannot combine it with `--allow-partial`, and provisional manual scores expire on the next `scan` unless replaced by trusted internal or attested-external imports.
11. If a batch fails, retry only that slice with `desloppify review --run-batches --packet <packet.json> --only-batches <idxs>`.
12. For Frost web frontend tasks, consult `docs/reference/frontend-web.md` and `DESIGN.md`, and run `cd clients/web && npm run check:static` before completion.

<!-- desloppify-overlay: codex -->
<!-- desloppify-end -->
