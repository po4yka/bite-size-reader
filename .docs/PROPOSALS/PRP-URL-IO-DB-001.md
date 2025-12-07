# Decouple Network IO from DB Writes in URL Pipeline
- Date: 2025-12-07
- Owner: AI Assistant (with user)
- Related Docs: .docs/TECH_DESIGNS/TD-URL-IO-DB-001.md, .docs/TESTING/TEST-URL-IO-DB-001.md, CLAUDE.md, SPEC.md

## Context
- Current URL flow interleaves Firecrawl/OpenRouter awaits with DB writes inside single coroutines, keeping network-bound semaphores occupied while persistence runs and coupling failure modes.
- We need better parallelism and resilience: network IO should not be serialized by DB latency; DB errors should not cancel in-flight IO.

## Goals
- Separate network-bound work (Firecrawl/LLM) from persistence/notifications so semaphores are released promptly.
- Preserve dedupe, caching, correlation IDs, and structured logging.
- Keep user-visible behavior stable (notifications, language handling, translation/insights) while improving throughput/resilience.

## Non-Goals
- Changing summary contract, prompts, or DB schema.
- Introducing a new message queue or storage engine.
- Altering access control or transport layers.

## Options Considered
- Option A: Stage awaits within existing coroutines: do network IO under semaphores, then persist/notify in follow-up awaits/tasks (no new infra).
- Option B: Background task queue/process for persistence and notifications (higher isolation, more infra/ops).
- Option C: Thread pool for persistence to avoid event-loop blocking (adds synchronization risk, less control).

## Decision
- Choose Option A: staged awaits with localized TaskGroups where helpful; ensure semaphores wrap only network calls; persist after IO completion; keep audit/log correlation.

## Risks / Trade-offs
- More control-flow branches; must ensure errors propagate and status updates remain consistent.
- Concurrency could surface latent DB race conditions; needs targeted tests and idempotent writes.

## Milestones / Timeline
- M1: Land tech design + test plan.
- M2: Refactor Firecrawl extraction staging and summarization staging.
- M3: Add async tests exercising DB latency and concurrency.

## Open Questions
- Do we need a feature flag to toggle staged persistence? (default: no, keep behavior consistent while improving performance)
