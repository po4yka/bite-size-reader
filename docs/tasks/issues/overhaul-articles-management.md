---
title: Overhaul articles management (filters, bulk actions, real signal) — frontend repo
status: blocked
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Overhaul articles management (filters, bulk actions, real signal) — frontend repo #repo/ratatoskr #area/frontend #status/blocked #blocked 🔼

    - blocked_reason: Bulk of the work lives in `ratatoskr-web/` (ArticlesPage.tsx, LibraryPage.tsx). The backend slices (server-side search/filters on /v1/summaries, batch endpoints, signal_score field on SummaryCompact) can land in this repo, but the consuming UI changes ship from the frontend repo.

## Goal

Make the All Articles + Library screens usable as a real workspace. Today users can only sort by date and click into a row. There is no real filtering, no bulk action surface, the Library search box does not query the API, and the Library `HIGH SIGNAL` filter relies on a `confidence` field that is not present on `SummaryCompact`.

## Concrete defects to fix

- `ratatoskr-web/src/features/articles/ArticlesPage.tsx`: `searchTerm` is local state only and never reaches the API; no filter beyond sort.
- `ratatoskr-web/src/features/library/LibraryPage.tsx`: hardcoded `limit:100, offset:0` (no real pagination); HIGH SIGNAL filter casts to `SummaryCompact & { confidence?: number }` — field is not in the API contract; INBOX/PENDING/TOTAL counters reflect only the loaded page; the `INGEST · SYNC ACTIVE` footer is a static literal.

## Scope split

### In this (backend) repo
- Add server-side `search`, `tag`, `collection`, `domain`, `language`,
  `favorited`, `read`, `from`, `to` query parameters to
  `GET /v1/summaries` (`app/api/routers/content/summaries.py`).
- **NOTE (2026-05-17 audit):** `SummaryCompact` at
  `app/api/models/responses/summaries.py:35` already exposes
  `confidence: float` (required). The frontend's
  `confidence?: number` cast in `LibraryPage.tsx` looks like
  stale defensive code rather than a missing backend field.
  Verify before adding a new `signal_score` field — the original
  task scope may have been resolved upstream and only the
  frontend cast needs cleanup. If a distinct `signal_score`
  semantic is still wanted, document the contract in
  `docs/SPEC.md` and back it with a deterministic computation
  (confidence × hallucination_risk_factor, say) rather than
  introducing a second free-form score.
- Add bulk-action POST endpoints: `/v1/summaries/bulk/mark-read`,
  `/v1/summaries/bulk/favorite`, `/v1/summaries/bulk/tag`,
  `/v1/summaries/bulk/add-to-collection`, `/v1/summaries/bulk/delete`.
- Replace offset pagination with keyset/cursor pagination on
  `/v1/summaries`.
- Wire Library footer ingest status to a real signal (existing
  ingestion telemetry).
- pytest coverage on the new endpoints and the signal_score field.

### In the ratatoskr-web frontend repo
- Wire ArticlesPage search to `GET /v1/summaries?search=...`.
- Add filters on both screens; deep-link via URL params.
- Bulk-action multi-select with optimistic update + rollback.
- Inline row actions: `m` mark read, `f` favorite, `t` tag, `d`
  delete, `c` collection — keyboard-bound.
- Saved views: persist `{filter, sort, search}` per user as named presets.
- Virtualize the row list for >500 items.

## Acceptance criteria

- [ ] Search + filter changes hit the API and update the URL (deep-linkable).
- [ ] Bulk actions: select 10 rows, mark all read in one request; UI updates optimistically and rolls back on error.
- [ ] HIGH SIGNAL filter is server-side; documented contract for the score in `docs/SPEC.md`.
- [ ] Library scrolls smoothly with 5000 rows in the dataset (virtualized).
- [ ] Saved views survive reload and tab close.
- [ ] New tests: pytest on batch endpoints; Playwright on filter + bulk-action flow; React Testing Library on saved-view persistence.
- [ ] `cd ratatoskr-web && npm run check:static && npm run test` passes; backend `make lint type` and pytest pass.

## References

- `ratatoskr-web/src/features/articles/ArticlesPage.tsx`
- `ratatoskr-web/src/features/library/LibraryPage.tsx`
- `app/api/routers/content/summaries.py`, `app/api/routers/content/search.py`
- [[run-frost-phase-7-mobile-regression]]
