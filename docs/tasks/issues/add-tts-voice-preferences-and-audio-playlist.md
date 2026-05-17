---
title: Add per-user TTS voice preference and multi-summary audio playlist endpoint
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add per-user TTS voice preference and multi-summary audio playlist endpoint #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/routers/user/tts.py:39-41` reads `voice_id`, `model_name`, `max_chars_per_request` only from the server config — no per-user override path. There is no playlist or batch-audio endpoint, only single-summary generation at `tts.py:53`. README markets TTS as a user feature, but today the product is single-summary, server-fixed-voice.

## User story

As a user with multiple summaries to listen to, I want to pick my preferred ElevenLabs voice and queue several summaries as a podcast playlist, so that I can listen on a commute.

## Context

- TTS handler: `app/api/routers/user/tts.py:39-41, :53`.
- No `playlist`, `voice_preference`, `tts_voice` references in `app/`.
- ElevenLabs adapter: `app/adapters/elevenlabs/tts_client.py`.

## Scope

- New endpoints: - `GET /v1/users/me/tts-preferences` → `{voice_id, model_name, speed, language}` (with defaults from server config). - `PUT /v1/users/me/tts-preferences` to update. - `POST /v1/summaries/audio/playlist` → accepts list of summary IDs + order, returns a manifest of playable audio URLs.
- Schema: extend `User.preferences_json` OR add typed `user_tts_preferences` table.
- TTS request handler consults per-user prefs before server config fallback.
- Web `/web/library` exposes a multi-select "Listen" action (covered by `ratatoskr-web` once spec lands).
- Document endpoints in OpenAPI spec and reference doc.

## Acceptance criteria

- [ ] Preferences round-trip through GET/PUT.
- [ ] Playlist endpoint returns audio URLs in requested order.
- [ ] Existing single-summary TTS continues to work for users with no preferences set.

## References

- TTS handler: `app/api/routers/user/tts.py:39-41, :53`
- ElevenLabs client: `app/adapters/elevenlabs/tts_client.py`
