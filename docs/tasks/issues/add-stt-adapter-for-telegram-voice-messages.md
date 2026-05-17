---
title: Add speech-to-text adapter for Telegram voice and audio messages
status: backlog
area: content
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add speech-to-text adapter for Telegram voice and audio messages #repo/ratatoskr #area/content #status/backlog ⏫

## Objective

Telegram voice-message MIME is already recognized (`app/adapter_models/telegram/telegram_enums.py:47` — `VOICE = "voice"`), but there is no STT adapter under `app/adapters/`. Sending a 30-second voice memo "summarize this idea" is the most natural mobile workflow today; the bot silently ignores it.

## User story

As a Telegram user on the go, I want to send a voice note to the bot and receive a summarized transcript back, so that I can capture ideas without typing.

## Context

- Voice MIME enum: `app/adapter_models/telegram/telegram_enums.py:47`.
- Whisper is mentioned in `docs/guides/configure-youtube-download.md:160` and `docs/explanation/faq.md:332` only as an optional YouTube transcript fallback — not as an inbound STT path.
- README lists Whisper as a future option.
- No `app/adapters/stt/` directory exists.

## Scope

- Create `app/adapters/stt/` with `STTClientProtocol` and at minimum a Whisper (OpenAI) implementation; optional Deepgram Nova-3 implementation as a second provider behind a factory similar to `app/infrastructure/embedding/embedding_factory.py`.
- In `app/adapters/telegram/message_router.py` (or the appropriate handler), branch on voice/audio attachment type → download via Telethon → POST to STT → reuse the existing summarization pipeline with the transcript as the "content" body.
- Persist transcripts (extend `crawl_results` schema with an optional `transcript` field OR add a new `voice_transcripts` table — pick the smaller-blast-radius option).
- Config: `STT_ENABLED`, `STT_PROVIDER`, `STT_API_KEY`, `STT_MAX_DURATION_SEC` (default 600 = 10 min).
- Metrics: `ratatoskr_stt_requests_total{outcome}`, `ratatoskr_stt_audio_seconds_total` for cost tracking.

## Acceptance criteria

- [ ] A voice memo sent to the bot produces a transcript + summary roundtrip.
- [ ] Audio files (mp3, m4a, ogg) sent as documents are also handled.
- [ ] Transcript persisted and visible in the summary detail view.
- [ ] Feature gated by env flag; bot ignores voice notes when off.

## References

- Voice MIME: `app/adapter_models/telegram/telegram_enums.py:47`
- Existing chain factory pattern: `app/adapters/content/scraper/factory.py`, `app/infrastructure/embedding/embedding_factory.py`
- Telethon download API: see existing usage in `app/adapters/telegram/`
