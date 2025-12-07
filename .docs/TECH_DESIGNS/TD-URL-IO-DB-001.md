# URL IO/DB Separation Tech Design
- Date: 2025-12-07
- Owner: AI Assistant (with user)
- Related Docs: .docs/PROPOSALS/PRP-URL-IO-DB-001.md, .docs/TESTING/TEST-URL-IO-DB-001.md, CLAUDE.md, SPEC.md

## Summary
Stage network-bound Firecrawl/OpenRouter calls separately from database writes in the URL pipeline. Semaphores should guard only network IO; persistence and notifications run after IO completes (or in lightweight TaskGroups), improving parallelism and resilience without changing user-visible behavior or contracts.

## Context & Problem
- Current `content_extractor` and `url_processor` interleave Firecrawl/LLM awaits with DB writes inside the same coroutine, holding semaphores during persistence and coupling failures.
- DB latency reduces throughput for Firecrawl/OpenRouter and raises user-visible latency; errors in persistence can cancel or delay network work.

## Goals / Non-Goals
- Goals: release semaphores immediately after network calls; isolate persistence/notifications; preserve dedupe, caching, correlation IDs, and structured logging.
- Non-Goals: change summary contract, prompts, DB schema, or access control.

## Assumptions & Constraints
- Python 3.13 async/await; semaphores provided via DI (`sem()` context).
- DB is SQLite via Peewee with async helpers; idempotent upserts exist.
- Keep existing notifications and audit hooks; no new infra/queues.

## Requirements Traceability
- Proposal PRP-URL-IO-DB-001: staged IO vs persistence, preserved behavior, improved resilience and parallelism.

## Architecture
- Extraction boundary: `ContentExtractor` handles network scrape under semaphore; persistence occurs after the semaphore is released.
- Summarization boundary: `URLProcessor` handles chunking/LLM under semaphore; persistence/notifications/translation/insights happen after IO completes.
- Use small `asyncio.TaskGroup` or follow-up awaits to run independent post-IO tasks without blocking network paths; ensure cancellation propagates and errors are logged with correlation IDs.

## Data Contracts
- No schema changes. Continue using existing crawl_results, requests, summaries, llm_calls tables and summary JSON contract.

## Flows
- Extraction flow:
  1) normalize + dedupe request (as today).
  2) Firecrawl `scrape_markdown` inside semaphore; do not persist inside the semaphore.
  3) After IO returns, persist crawl result and send notifications; salvage path also stages persistence after network fetch.
- Summarization flow:
  1) Determine chunking and system prompt.
  2) Run chunked or single-pass LLM calls under semaphore only.
  3) After IO, persist summaries/status/insights; translations/insights can run in TaskGroup if independent; ensure request status updates remain serialized.

## Algorithms / Logic
- Dedupe hashing, language detection, chunking thresholds, and validation remain unchanged.
- Add helper(s) to persist summaries/insights separately from LLM calls; reuse existing audit logging.

## Error Handling & Retries
- If persistence fails after IO, log with correlation ID and audit; attempt best-effort status update; do not re-issue network calls.
- Preserve existing Firecrawl and OpenRouter retry/backoff behavior.
- Ensure TaskGroup tasks shield main result handling failures: collect/log exceptions, propagate fatal ones that compromise correctness.

## Security & Privacy
- No changes: owner-only access, redact Authorization headers, no PII beyond IDs.

## Performance & Scalability
- Semaphores freed sooner to increase concurrent Firecrawl/OpenRouter throughput.
- DB work remains serialized per request where needed (status updates) but off the critical network path.

## Operations
- Maintain structured logging with `cid`; keep audit hooks on persistence steps.
- Feature flags not required; behavior should stay compatible.

## Testing Strategy
- Unit/integration tests simulate DB latency while concurrent network mocks run; assert semaphore-backed concurrency is unaffected.
- Validate dedupe behavior, status updates, and translation/insights flows still execute.

## Risks / Trade-offs
- Additional control-flow complexity; must avoid double-persist or missed status updates.
- Potential hidden DB race conditions; rely on idempotent upserts and targeted tests.

## Alternatives Considered
- Background queue/process for persistence (more isolation, higher ops cost).
- Thread pool for persistence (added synchronization risk; less preferred).

## Open Questions
- Should we add a feature flag for staged persistence? Not planned unless testing reveals regressions.
