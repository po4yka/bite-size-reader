---
title: Add per-route ErrorBoundary wrappers in manifest.tsx
status: backlog
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add per-route ErrorBoundary wrappers in manifest.tsx #repo/ratatoskr #area/frontend #status/backlog 🔼

## Objective

A single `ErrorBoundary` wraps the entire `<Outlet>` in `AppShell.tsx:199`. A crash in any feature page blanks the entire app. Per-route boundaries allow graceful degradation — a broken search page doesn't take down the library or submit pages.

## Context

- `clients/web/src/components/AppShell.tsx:199` — single top-level boundary
- `clients/web/src/routes/manifest.tsx` — route definitions with lazy loading
- `clients/web/src/components/ErrorBoundary.tsx` — existing boundary component

## Acceptance criteria

- [ ] Each lazy-loaded route in `manifest.tsx` wraps its component in an `ErrorBoundary`
- [ ] The fallback UI uses design system tokens (not inline style as in the current `ErrorBoundary.tsx:38-40`)
- [ ] An error in one route does not affect navigation to other routes
- [ ] The top-level boundary in `AppShell` remains as a last-resort catch

## Definition of done

Throwing an error in `SearchPage` renders the page-level error fallback while the navigation shell remains intact.
