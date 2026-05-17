---
title: Ship browser extension (Manifest V3) for /v1/quick-save
status: backlog
area: frontend
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Ship browser extension (Manifest V3) for /v1/quick-save #repo/ratatoskr #area/frontend #status/backlog 🔽

## Objective

`app/api/routers/quick_save.py:1` documents itself as "Quick-Save endpoint for browser extension" with a documented request body at `app/api/models/requests.py:369` and OpenAPI spec at `docs/openapi/mobile_api.yaml:6270`. **The server contract is locked; the extension code does not exist** — no `extension/` or `webextension/` directory at the repo root. Shipping the extension unlocks one-click capture from any tab on Chrome / Firefox / Edge.

## User story

As a power user reading articles in the browser, I want a one-click button to send the current tab to Ratatoskr, so that I don't have to copy-paste the URL into Telegram.

## Context

- Server endpoint: `app/api/routers/quick_save.py:1`.
- Request model: `app/api/models/requests.py:369`.
- Spec: `docs/openapi/mobile_api.yaml:6270`.

## Scope

- Repo-root directory `extension/` (or a separate sibling repo — decide which fits team workflow).
- Manifest V3 extension supporting Chrome, Firefox, Edge.
- Auth via the existing JWT flow (credential or magic-link login in a popup; token stored in `chrome.storage.session`).
- Single toolbar button that POSTs to `/v1/quick-save` with current URL, page title, selected text.
- Success / failure feedback in the popup; offline queue with retry on reconnect.
- Distributable .zip artifact built by CI (Chrome Web Store / AMO submission left manual).
- README in the extension directory with screenshots.

## Acceptance criteria

- [ ] Extension installs locally in Chrome and Firefox.
- [ ] One click on a typical article tab → summary appears in user's library.
- [ ] Offline queue replays when network comes back.
- [ ] CI produces a release-ready zip.

## References

- Endpoint: `app/api/routers/quick_save.py:1`
- Request body: `app/api/models/requests.py:369`
- Spec: `docs/openapi/mobile_api.yaml:6270`
