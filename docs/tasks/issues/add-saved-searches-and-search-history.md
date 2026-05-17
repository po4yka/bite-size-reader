---
title: Add saved searches and opt-in search history
status: backlog
area: api
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add saved searches and opt-in search history #repo/ratatoskr #area/api #status/backlog 🔽

## Objective

`app/api/routers/content/search.py` exposes `/search`,
`/search/semantic`, `/topics/trending`, `/search/insights`,
`/topics/related`, `/urls/check-duplicate`, but no
`/search/saved` or `/search/history`. Frontend has a powerful
search UI (`docs/reference/frontend-web.md:232-238` describes
mode + filter complexity) but no way to bookmark a query.

## User story

As a heavy user, I want to save a frequently-used search (query +
filters) and re-run it with one click, so that I don't re-type
`tag:rust mode:hybrid lang:en` every morning.

## Context

- Search router:
  `app/api/routers/content/search.py`.
- Frontend filter doc:
  `docs/reference/frontend-web.md:232-238`.
- Grep for `saved_search`, `search_history`, `saved-search` →
  zero hits across `app/` and `docs/`.

## Scope

- Schema: new `saved_searches` table
  (user_id, name, query, filters_json, created_at).
- Endpoints:
  - `GET /v1/searches/saved`, `POST /v1/searches/saved`,
    `DELETE /v1/searches/saved/{id}`.
  - `POST /v1/searches/saved/{id}/run` returns search results
    using the stored params.
- Optional `search_history` ring buffer (last 50, opt-in via
  user preference); endpoint
  `GET /v1/searches/history` and `DELETE /v1/searches/history`.
- Web `/web/search` adds a "Save this search" button (covered
  by `ratatoskr-web`).
- Document in OpenAPI spec + reference doc.

## Acceptance criteria

- [ ] Saved-search CRUD round-trips.
- [ ] Run-saved endpoint returns identical results to the
  equivalent direct search.
- [ ] History is off by default and can be cleared.

## References

- Router: `app/api/routers/content/search.py`
- Frontend:
  `docs/reference/frontend-web.md:232-238`
