---
title: Add integration test for submit URL → poll → view summary critical path
status: backlog
area: testing
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add integration test for submit URL → poll → view summary critical path #repo/ratatoskr #area/testing #status/backlog ⏫

## Objective

The main user flow — submit a URL, poll for completion, navigate to the summary — has zero test coverage. This is the highest-value path in the application and the most likely to regress during refactors.

## Context

- `clients/web/src/features/submit/SubmitPage.tsx` — no test file exists
- `clients/web/src/testing/render.tsx` — test infrastructure with `renderWithProviders` and MSW-based API mocking
- `clients/web/src/api/requests.ts` — submission API client

## Acceptance criteria

- [ ] Test renders `SubmitPage`, enters a URL, submits, and polls until a mock "completed" response
- [ ] Test verifies navigation to the article detail page on completion
- [ ] Test covers the error path (submission fails with a 4xx response)
- [ ] Uses `renderWithProviders` + MSW handlers, no real network calls

## Definition of done

`npm run test` includes at least 3 new passing test cases for the submission flow.
