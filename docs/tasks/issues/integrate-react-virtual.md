---
title: Add @tanstack/react-virtual to LibraryPage for 100-item list virtualization
status: backlog
area: frontend
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add @tanstack/react-virtual to LibraryPage for 100-item list virtualization #repo/ratatoskr #area/frontend #status/backlog 🔽

## Objective

`LibraryPage` fetches up to 100 summaries and renders them all unconditionally. Keyboard cursor tracking (`useState` for active index) triggers a full list re-render on every keypress. With 100 items this causes visible jank on lower-end devices (Telegram Mini App target).

## Context

- `clients/web/src/features/library/LibraryPage.tsx` — renders full list, cursor state causes re-renders
- `@tanstack/react-virtual` is not currently a dependency; `@tanstack/react-query` is already installed (same org, compatible versioning)

## Acceptance criteria

- [ ] `@tanstack/react-virtual` added to `package.json` dependencies
- [ ] `LibraryPage` uses `useVirtualizer` for the summary list
- [ ] Keyboard navigation (cursor up/down, Enter) works correctly with virtual rows
- [ ] List scroll position is preserved on back-navigation

## Definition of done

DevTools Performance profile shows no full-list re-render on cursor key press; only visible rows are in the DOM.
