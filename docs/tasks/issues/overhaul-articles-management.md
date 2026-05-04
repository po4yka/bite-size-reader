---
title: Overhaul articles management (filters, bulk actions, real signal)
status: backlog
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Overhaul articles management (filters, bulk actions, real signal) #repo/ratatoskr #area/frontend #status/backlog 🔼

## Goal

Make the All Articles + Library screens usable as a real workspace. Today users can only sort by date and click into a row. There is no real filtering, no bulk action surface, the Library search box does not query the API, and the Library `HIGH SIGNAL` filter relies on a `confidence` field that is not present on `SummaryCompact`.

## Concrete defects to fix

- `clients/web/src/features/articles/ArticlesPage.tsx`: `searchTerm` is local state only and never reaches the API; no filter beyond sort.
- `clients/web/src/features/library/LibraryPage.tsx`: hardcoded `limit:100, offset:0` (no real pagination); HIGH SIGNAL filter casts to `SummaryCompact & { confidence?: number }` — field is not in the API contract; INBOX/PENDING/TOTAL counters reflect only the loaded page; the `INGEST · SYNC ACTIVE` footer is a static literal.

## Scope

- Wire ArticlesPage search to `GET /v1/summaries?search=...`.
- Add filters on both screens: read/unread, favorited, language, source domain, topic tag, collection, date range.
- Add a real `confidence` (or rename to `signal_score`) to the `SummaryCompact` API model so the HIGH SIGNAL filter is server-side.
- Replace Library's offset pagination with cursor/keyset pagination; virtualize the row list for >500 items.
- Bulk actions in ArticlesPage: multi-select rows + apply mark read/unread, favorite, add tag, add to collection, delete.
- Inline row actions on Library: `m` mark read, `f` favorite, `t` tag, `d` delete, `c` collection — all keyboard-bound.
- Saved views: persist `{filter, sort, search}` per user as named presets.
- Wire the Library footer ingest status to a real signal.

## Acceptance criteria

- [ ] Search + filter changes hit the API and update the URL (deep-linkable).
- [ ] Bulk actions: select 10 rows, mark all read in one request; UI updates optimistically and rolls back on error.
- [ ] HIGH SIGNAL filter is server-side; documented contract for the score in `docs/SPEC.md`.
- [ ] Library scrolls smoothly with 5000 rows in the dataset (virtualized).
- [ ] Saved views survive reload and tab close.
- [ ] New tests: pytest on batch endpoints; Playwright on filter + bulk-action flow; React Testing Library on saved-view persistence.
- [ ] `cd clients/web && npm run check:static && npm run test` passes; backend `make lint type` and pytest pass.

## References

- `clients/web/src/features/articles/ArticlesPage.tsx`
- `clients/web/src/features/library/LibraryPage.tsx`
- `app/api/routers/summaries.py`, `app/api/routers/search.py`
- [[run-frost-phase-7-mobile-regression]]
