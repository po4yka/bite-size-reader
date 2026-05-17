---
title: Add unit tests for digest pipeline modules (channel reader, formatter, analyzer)
status: backlog
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add unit tests for digest pipeline modules (channel reader, formatter, analyzer) #repo/ratatoskr #area/testing #status/backlog 🔼

## Objective

Several non-trivial digest modules have no dedicated test files; their behaviour is only exercised via the scheduler integration test. User-visible logic (dedup, fallback messaging, LLM error handling) is currently untested at the unit level, making targeted regressions hard to catch.

## Context

- `app/adapters/digest/digest_service.py` (359 LOC).
- `app/adapters/digest/channel_reader.py` (203 LOC) — disable-on- error behaviour at line 78.
- `app/adapters/digest/formatter.py` (172 LOC).
- `app/adapters/digest/analyzer.py` (198 LOC).
- `app/adapters/digest/userbot_client.py`.
- Existing coverage: `tests/test_digest_session_validator.py`, `tests/api/test_digest_router.py`, `tests/tasks/test_digest_task.py`, `tests/integration/test_channel_digest_scheduler.py`.
- Missing: `test_channel_reader.py`, `test_formatter.py`, `test_analyzer.py`, `test_userbot_client.py`.

## Scope

- Add `tests/adapters/digest/test_channel_reader.py`: - Disable-on-error fallback when Telegram raises. - Channel-removed (404 from userbot) handling.
- Add `tests/adapters/digest/test_formatter.py`: - Empty post set → fallback message. - Partial post set (some analyses missing) → graceful render. - Telegram length limit enforcement.
- Add `tests/adapters/digest/test_analyzer.py`: - LLM error fallback returns stub analysis. - Schema-validation failure marks the post `analysis_failed`.
- Optional: `tests/adapters/digest/test_userbot_client.py`: - Reconnect retry behaviour mocked.

## Acceptance criteria

- [ ] Four new test files exercising the listed scenarios.
- [ ] All new tests pass under standard pytest harness.
- [ ] No new flakiness — async tests use deterministic event-loop fixtures.

## References

- Pipeline: `app/adapters/digest/digest_service.py`
- Channel reader: `app/adapters/digest/channel_reader.py:78`
- Formatter: `app/adapters/digest/formatter.py`
- Analyzer: `app/adapters/digest/analyzer.py`
- Related: [[add-channel-digest-metrics-and-alerts]]
