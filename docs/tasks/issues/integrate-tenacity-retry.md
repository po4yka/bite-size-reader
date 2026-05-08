---
title: Evaluate splitting OpenRouter transport retry from the logical state machine and apply tenacity to the transport layer
status: backlog
area: llm
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-08
---

- [ ] #task Evaluate splitting OpenRouter transport retry from the logical state machine and apply tenacity to the transport layer #repo/ratatoskr #area/llm #status/backlog 🔽

## Background — original spec was inaccurate

The 2026-05-04 spec asked to "replace bespoke retry loops in OpenRouter and Firecrawl adapters with tenacity." A 2026-05-08 audit against the code found the premise wrong on two counts:

- **`app/adapters/content/content_extractor.py` has no retry loop.** `rg 'for attempt|range\(.*retries' app/adapters/content/` returns zero matches. The file sets `retryable=True` on extracted errors so callers can decide policy, but there is no manual retry to replace.
- **`app/adapters/openrouter/chat_attempt_runner.py:52` is a state machine, not a retry loop.** Each iteration mutates `state.request` (downgrades `stream=True` → `False`), `rf_mode_current` and `response_format_current` (downgrades `json_schema` → `json_object` → `off`), and `state.request.max_tokens` (raises ceiling on truncation). It branches on `outcome.should_retry`, `outcome.should_try_next_model`, `outcome.success` — three different exit signals — and only sometimes calls `sleep_backoff` based on `outcome.retry.backoff_needed`. `tenacity.@retry` re-invokes a callable with the same arguments on raised exceptions; it cannot model "retry with a different request shape based on what the last response said."

Mechanically satisfying the original DoD (`rg 'for.*attempt|while.*retry'` returns zero) would require either (a) wrapping the state machine in a class that exposes a tenacity-callable shim, which is more code than the current loop, or (b) deleting the per-attempt request mutation, which loses the schema-downgrade and stream-fallback capabilities the loop exists for.

## Reframed objective

The only real "transport-level retry" hidden inside the state machine is the bare `except Exception` branch at `chat_attempt_runner.py:68-78`: catch any exception from `_transport.attempt_request`, sleep, retry the same call. This sub-fragment IS amenable to `tenacity` — it's a network-error retry with backoff and a max-attempts cap, no request mutation.

If the maintainer chooses to take this on, the work is:

1. Extract `_transport.attempt_request` into a tenacity-decorated helper that retries on `httpx.HTTPError` / connection-class exceptions, leaving non-network errors to bubble up.
2. The remaining state-machine loop in `_run` then handles only **logical** retries (response-format downgrade, stream fallback, truncation recovery). It still iterates, but no longer catches transport errors itself.
3. Configurable via `AppConfig.openrouter` (max attempts, initial wait, max wait).
4. `tenacity` added to core dependencies.

## Acceptance criteria (reframed)

- [ ] Decision recorded: keep the current single-loop design (close this issue), or proceed with the transport/logical split.
- [ ] If proceeding: only the **transport-error** branch of `chat_attempt_runner.py` (currently lines 68-78) moves under tenacity. The state-machine loop stays.
- [ ] `tenacity` added to core deps; transport retry config sourced from `AppConfig`, not hardcoded.
- [ ] Existing OpenRouter retry tests (`tests/test_openrouter_chat_attempt_runner.py`) pass unchanged.
- [ ] No change to `app/adapters/content/` — there is no retry loop there to replace.

## Definition of done

Issue is either closed with rationale (state machine fits the problem; tenacity adds nothing), or the transport-retry slice is shipped with passing tests and `pyproject.toml` updated.

## Audit notes (2026-05-08)

- Verified: `app/adapters/openrouter/chat_attempt_runner.py:52-168` is a stateful retry loop, not a simple network retry.
- Verified: `app/adapters/content/content_extractor.py` has zero retry loops.
- Verified: `tenacity` is not in `pyproject.toml` dependencies.
- Existing related tests: `tests/test_openrouter_chat_attempt_runner.py`, `tests/test_retry_utils.py`.
