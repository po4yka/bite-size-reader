---
title: Integrate sentry-sdk for backend FastAPI and frontend React error tracking
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Integrate sentry-sdk for backend FastAPI and frontend React error tracking #repo/ratatoskr #area/observability #status/backlog 🔼

## Objective

No production error tracking exists. `ErrorBoundary.tsx` uses `console.error` only; background task failures in the API are logged to stdout but not alerted. Silent failures in summarization, scraper chain, and YouTube download go undetected until a user reports them.

## Context

- `clients/web/src/components/ErrorBoundary.tsx:24` — `console.error` only
- `app/api/main.py` — FastAPI exception handlers log but do not alert
- Sentry free tier covers single-project use; self-hosted Glitchtip is an alternative

## Acceptance criteria

- [ ] `sentry-sdk[fastapi,loguru]` added to `monitoring` extra in `pyproject.toml`
- [ ] `@sentry/react` added to frontend dev dependencies and initialized in `main.tsx`
- [ ] `SENTRY_DSN` env var added to `app/config/settings.py` (optional, monitoring disabled if absent)
- [ ] `ErrorBoundary.tsx` calls `Sentry.captureException` before `console.error`
- [ ] Correlation ID attached to every Sentry event as a tag

## Definition of done

A thrown error in a feature page appears in the Sentry dashboard with the correlation ID visible.
