---
title: Add first-time onboarding flow and typed user profile
status: backlog
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add first-time onboarding flow and typed user profile #repo/ratatoskr #area/frontend #status/backlog 🔼

## Objective

The Telegram side has an `onboarding_handler.py` but the API +
web side stores preferences as a free-form `preferences_json`
dict (`app/api/routers/user/user.py:51-141`) with no schema and
hardcoded defaults (`{"theme": "dark", "font_size": "medium"}` at
line 61). There is no `onboarding_completed` flag in
`app/db/models/`. The web frontend (`docs/reference/frontend-web.md:134-151`
lists 14 routes) has no `/web/onboarding` or `/web/welcome`. New
users land directly in `/web/library` with no walkthrough.

## User story

As a new user opening Ratatoskr for the first time, I want a
guided onboarding that explains what to send the bot and lets me
set my language / theme / voice preference, so that I am not
staring at an empty library.

## Context

- Telegram onboarding (good):
  `app/adapters/telegram/command_handlers/onboarding_handler.py`.
- API preferences (weak):
  `app/api/routers/user/user.py:51-141`.
- Frontend routes:
  `docs/reference/frontend-web.md:134-151`.

## Scope

- Schema: add `onboarding_completed_at`, `locale`, `theme`,
  `display_name`, `default_summary_language` as typed columns on
  `User`, OR introduce a `user_profiles` table.
- `GET /v1/users/me` exposes a typed `profile` object alongside
  the existing data.
- `POST /v1/users/me/onboarding/complete` marks the user as
  onboarded.
- Frontend `/web/onboarding` route (separate ratatoskr-web work)
  shown until completed.
- Bot `/start` aligns language / copy with the web onboarding
  strings so both surfaces feel coherent.
- Document the typed profile shape in
  `docs/reference/mobile-api.md`.

## Acceptance criteria

- [ ] Typed profile round-trips through GET/PUT.
- [ ] `onboarding_completed_at` set when the user marks complete.
- [ ] Existing untyped `preferences_json` migrated cleanly
  (back-compat).
- [ ] Spec + reference doc updated.

## References

- API: `app/api/routers/user/user.py:51-141`
- Bot: `app/adapters/telegram/command_handlers/onboarding_handler.py`
- Frontend reference:
  `docs/reference/frontend-web.md:134-151`
