# Project Goals (Overview)
- Date: 2025-12-07
- Owner: AI Assistant (with user)
- Related Docs: CLAUDE.md, SPEC.md, README.md

## Purpose
Establish shared goals and guardrails for Bite-Size Reader so code and docs stay aligned as we evolve Telegram + content summarization flows.

## Product Goals
- Deliver concise, contract-valid summaries for web articles, YouTube videos, and forwarded Telegram messages.
- Keep owner-only access control enforced end-to-end (Telegram, API, storage).
- Persist every artifact (messages, crawls, LLM calls, summaries) for traceability and analytics.
- Provide resilient, low-latency processing with clear user-visible status and correlation IDs.
- Support multi-language flows (en/ru) with prompts kept in sync.

## Non-Goals
- Building a multi-tenant SaaS; only owner-whitelisted users are supported.
- Long-term content hosting or public search frontends.
- Replacing Firecrawl/OpenRouter with self-hosted equivalents in this phase.

## Stakeholders
- Owner/operator of the bot.
- Telegram bot users (whitelisted).
- Mobile API consumers (if enabled).
- Engineering/ML contributors maintaining adapters, prompts, and DB schema.

## Success Metrics
- P95 end-to-end latency per request within configured timeout (`REQUEST_TIMEOUT_SEC`).
- <1% user-visible failures per week with correlation IDs logged.
- Summaries pass strict JSON contract validation and language choice matches detection/preference.
- No unauthorized access (ALLOWED_USER_IDS enforcement).

## Current Scope
- Async Telegram bot backed by Firecrawl (content) and OpenRouter (LLM) with SQLite persistence.
- YouTube support (transcripts + 1080p download) gated by configuration.
- Mobile API (FastAPI) with JWT + Telegram auth when enabled.

## Future Opportunities
- Improve resilience via staged IO/DB separation and better concurrency controls.
- Expand observability (metrics/traces) and fine-grained rate limiting.
- Extend prompt variants and multilingual coverage while preserving contract compliance.
