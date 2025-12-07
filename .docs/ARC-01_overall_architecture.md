# Overall Architecture (Bite-Size Reader)
- Date: 2025-12-07
- Owner: AI Dev Partner
- Status: Draft

## System Context
- Single Dockerized service exposing Telegram bot, CLI, and optional FastAPI mobile API.
- Integrations: Firecrawl for extraction, OpenRouter for LLM, YouTube (yt-dlp + transcripts), SQLite for persistence.

## High-Level Components
- Adapters: Telegram, content (Firecrawl/YouTube), OpenRouter, external formatters.
- Core: URL normalization, summary contract, language detection, logging.
- Pipeline: Request routing → extraction → chunking/summarization → validation → formatting → persistence.
- Agents: Extraction, summarization, validation with orchestrator.
- Services: Search (vector/hybrid), embeddings, topic search, background tasks.

## Data & Storage
- SQLite at /data for requests, crawl results, LLM calls, summaries, videos metadata.
- File storage under /data/videos for downloads; backups under /data/backups.

## Flows (simplified)
- URL: Normalize → dedupe → Firecrawl → quality checks → summarize → validate JSON → reply + persist.
- YouTube: Detect → download + transcript → summarize → validate → reply + persist.
- Forwarded posts: Extract text → summarize → validate → reply + persist.

## Non-Functional Notes
- Async throughout (Pyrogram, httpx, Peewee async patterns).
- Rate limiting/semaphores for external APIs; retries with backoff.
- Structured logging with correlation IDs; redact Authorization headers.

## Security & Access
- Owner-only access via ALLOWED_USER_IDS.
- Secrets via environment variables; no secrets in DB/logs.

## Observability
- Persist Firecrawl/LLM artifacts; notifications for major pipeline steps.
- Use correlation IDs to trace through DB records and logs.
# Overall Architecture
- Date: 2025-12-07
- Owner: AI Assistant (with user)
- Related Docs: CLAUDE.md, SPEC.md, README.md, .docs/OVERVIEW-01_project_goals.md

## Summary
Bite-Size Reader is an async Telegram-first pipeline: incoming messages are normalized and access-controlled, routed to URL/forward processors, extracted via Firecrawl or YouTube downloader, summarized via OpenRouter, validated against a strict JSON contract, and persisted in SQLite with structured logging and correlation IDs. Optional FastAPI endpoints expose summaries for mobile clients.

## Layers & Responsibilities
- Transport: Telegram adapter (`app/adapters/telegram/*`), FastAPI (`app/api/*`), CLI tools.
- Content Pipeline: URL processor, content extractor (Firecrawl/YouTube), chunker, LLM summarizer, validation agents.
- Core Utilities: URL normalization, summary contract validation, language detection, logging.
- Persistence: SQLite via Peewee (`app/db/*`), storing requests, crawls, LLM calls, summaries, videos.
- Services/Agents: Multi-agent orchestration for extraction, summarization, validation; search/embedding services for retrieval features.

## Key Flows (high level)
1) Telegram message → Access check → Message router → URL handler.
2) URL flow: normalize + dedupe → Firecrawl/YouTube extraction (async, rate-limited) → content chunking or direct summarization → JSON validation → responses + persistence.
3) Forwarded content: direct summarization/validation with caching and persistence.
4) Mobile API: auth (Telegram login + JWT), summary retrieval/sync with rate limiting and envelopes.

## Data Contracts & Storage
- Summary JSON contract enforced in `app/core/summary_contract.py` with language-aware prompts in `app/prompts/en|ru`.
- SQLite schema: users, chats, requests, telegram_messages, crawl_results, video_downloads, llm_calls, summaries; videos under `/data/videos` when enabled.

## Performance & Resilience Notes
- Async throughout; semaphores for Firecrawl/OpenRouter concurrency.
- Deduplication via normalized URL hash to avoid redundant work.
- Structured logging with correlation IDs; retries and fallbacks for Firecrawl/LLM where applicable.

## Security & Operations
- Owner-only access via `ALLOWED_USER_IDS`; secrets from env vars.
- Redact Authorization in logs; no PII beyond user/chat IDs.
- Dockerized single-container deployment with `/data` volume for DB/downloads.
