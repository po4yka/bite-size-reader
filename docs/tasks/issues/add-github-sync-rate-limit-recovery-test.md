---
title: Add integration test that GitHub sync survives 429 and resumes next run
status: backlog
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add integration test that GitHub sync survives 429 and resumes next run #repo/ratatoskr #area/testing #status/backlog 🔼

## Objective

`app/tasks/github_sync.py:179-193` records per-user errors on
`GitHubRateLimitError` and continues, but there is no integration
test asserting that:

1. A 429 for user A does not prevent user B's sync from completing.
2. User A is reprocessed on the next tick.

A refactor of the per-user error handling could silently break
this contract without any test failing.

## Context

- Rate-limit handling: `app/tasks/github_sync.py:179-193`.
- `rg "GitHubRateLimitError" tests/` matches only the raising
  unit test at `tests/adapters/github/test_github_api_client.py`.
- `tests/tasks/test_github_sync.py` has no per-user-error
  scenario.

## Scope

- New integration test in `tests/tasks/test_github_sync.py`:
  - Set up two users with stored integrations.
  - Inject `GitHubRateLimitError` for user A's first call.
  - Assert: the sync run completes, user B is fully processed,
    user A is recorded as deferred.
  - Re-run the sync (simulate next cron tick) — assert user A is
    now processed and the deferred state is cleared.

## Acceptance criteria

- [ ] New test covers per-user-error isolation.
- [ ] New test covers deferred-user resume on the next run.
- [ ] Tests run inside the standard pytest harness (no live
  GitHub calls).

## References

- Task: `app/tasks/github_sync.py:179-193`
- Existing tests: `tests/tasks/test_github_sync.py`
- Test helpers: `tests/db_helpers.py`
- Related: [[add-github-sync-rate-limit-and-budget-alerts]]
