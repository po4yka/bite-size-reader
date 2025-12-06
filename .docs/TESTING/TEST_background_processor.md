# Background Processor Hardening Test Plan
- Date: 2025-12-06
- Author: AI Partner

## Scope
- Mobile API background processor refactor: DI wiring, Redis idempotent lock, structured errors, and exponential-backoff retries for extraction/LLM across URL and forward requests.

## Test Types
- Unit: lock acquisition/release (Redis + fallback), backoff delay calculation, structured error mapping, builder wiring.
- Integration: end-to-end process invocation with fakeredis, ensuring single summary write and status transitions.
- E2E: Not covered in this iteration; FastAPI routes already exercised by integration scope.

## Environments / Data
- Config: Redis enabled with prefix `bsr`, background lock TTL default; fallback path with Redis disabled.
- Fixtures: Fake Request/Summary rows; fakeredis client; stub URL/LLM processors returning deterministic outputs; correlation_id fixture.

## Test Cases
- TC1: DI builder returns BackgroundProcessor with injected deps and semaphore respecting `max_concurrent_calls`.
- TC2: Lock held in Redis causes skip without processing; logs `lock_held` and leaves status unchanged.
- TC3: Redis unavailable -> fallback in-process lock used; processing still succeeds once.
- TC4: Backoff helper produces bounded exponential delays with jitter and respects attempts/max delay.
- TC5: URL request processing success path writes summary once, sets status `success`, uses correlation_id in logs.
- TC6: Extraction failure triggers retries then status `error` with structured error payload saved/logged.
- TC7: Forward request processing uses language detection fallback and upserts summary; idempotent when summary already exists (no duplicate).

## Non-Functional
- Resiliency: lock TTL prevents orphaned locks; retries bounded to configured attempts/delay cap.

## Exit Criteria
- All unit and integration tests in `tests/api/test_background_processor.py` pass under `uv run pytest tests/api/test_background_processor.py`.
