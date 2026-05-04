---
title: Replace SearchPage 10x useState filter state with useSearchParams
status: backlog
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Replace SearchPage 10x useState filter state with useSearchParams #repo/ratatoskr #area/frontend #status/backlog 🔼

## Objective

`SearchPage.tsx:36-46` has 10 separate `useState` calls for filter state (query, date range, sort, tags, etc.). This state is lost entirely on back-navigation. Using `useSearchParams` (built into react-router-dom v7, already installed) makes search state bookmarkable and back-button–preserving with zero new dependencies.

## Context

- `clients/web/src/features/search/SearchPage.tsx:36-46` — 10 independent `useState` calls
- react-router-dom v7 is already a dependency (`useSearchParams` available)
- `setPage(1)` is called in every filter handler, causing scroll-to-top on each change

## Acceptance criteria

- [ ] All 10 filter state variables replaced with a single `useSearchParams`-backed state object
- [ ] Filter state survives browser back/forward navigation
- [ ] Search URL is bookmarkable (sharing the URL reproduces the same search)
- [ ] `setPage(1)` behaviour preserved when filters change

## Definition of done

Performing a search, navigating to an article, and pressing back returns to the same search with filters intact.
