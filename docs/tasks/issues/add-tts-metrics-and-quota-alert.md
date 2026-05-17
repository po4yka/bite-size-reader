---
title: Add ElevenLabs TTS metrics and quota-exhaustion alert
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add ElevenLabs TTS metrics and quota-exhaustion alert #repo/ratatoskr #area/observability #status/backlog 🔼

## Objective

The ElevenLabs TTS adapter only emits structured logs; there are no Prometheus counters for request count, synthesized bytes, retry rate, or quota exhaustion. TTS is a paid external service with quota and rate-limit ceilings — operators need cost and failure visibility to catch a runaway loop or expired key before users surface it.

## Context

- Client: `app/adapters/elevenlabs/tts_client.py:30-203` — logs only (`elevenlabs_retry` at :152, `elevenlabs_http_error_retry` at :168).
- `ElevenLabsQuotaExceededError` raised at `app/adapters/elevenlabs/tts_client.py:196` — uncounted.
- `rg "tts|ELEVENLABS" app/observability/` returns nothing.

## Scope

- New counters: - `ratatoskr_tts_requests_total{outcome}` (`success`, `retry`, `quota_exceeded`, `http_error`, `timeout`). - `ratatoskr_tts_audio_bytes_total` (running sum of bytes synthesized, for cost tracking).
- New histogram: `ratatoskr_tts_latency_seconds`.
- Alert: any `quota_exceeded` outcome → severity warning, `for: 0m`.
- Alert: `http_error` rate > 5% over 15m → severity warning.

## Acceptance criteria

- [ ] Metrics registered in `app/observability/` and incremented in the TTS client.
- [ ] Two alert rules in `ops/monitoring/alerting_rules.yml`.
- [ ] Unit test asserts each counter increments on the relevant exception path.

## References

- Client: `app/adapters/elevenlabs/tts_client.py:30-203`
- Adapter: `app/adapters/elevenlabs/`
