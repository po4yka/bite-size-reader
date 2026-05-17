---
title: Add GitHub repo "watch" subscriptions with README-diff and release alerts
status: backlog
area: content
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add GitHub repo "watch" subscriptions with README-diff and release alerts #repo/ratatoskr #area/content #status/backlog 🔼

## Objective

`app/tasks/github_sync.py:312-344` updates `Repository.watchers` (GitHub's count) on every sync, but there is no `UserRepositoryWatch` model and no per-user notification when a watched repo's README materially changes or a new release ships. The architecture doc `docs/explanation/github-repository-ingestion.md` mentions "webhook-based incremental sync" as a future direction; this issue stays within the existing daily-cron architecture.

## User story

As someone who indexes my GitHub stars, I want to mark certain repos as "watched" so that I get a notification (push or Telegram) when their README materially changes or a new release ships.

## Context

- Daily sync: `app/tasks/github_sync.py:312-344`.
- Existing model: `app/db/models/repository.py` — no `UserRepositoryWatch` table.
- Grep for `repo_watch`, `repo.*subscription`, `readme.*diff` across `app/` returns zero.

## Scope

- Schema: new `user_repository_watches` table (user_id, repository_id, watch_readme, watch_releases, created_at).
- Endpoints: - `POST /v1/repositories/{id}/watch` and `DELETE /v1/repositories/{id}/watch`. - `GET /v1/repositories/watched` lists watched repos.
- Daily sync extension: for each watched repo, compute `sha256(readme_body)` + latest-release-tag delta vs last sync.
- On change: emit `RepositoryWatchTriggered` event consumed by the push handler (covered by [[wire-push-notifications-into-event-bus]]) and a Telegram notifier.
- Document in OpenAPI spec + reference doc.

## Acceptance criteria

- [ ] User can watch / unwatch a repo via API.
- [ ] README change triggers exactly one notification per change (idempotent).
- [ ] New release-tag triggers exactly one notification.
- [ ] Watch state persists across sync runs.

## References

- Sync task: `app/tasks/github_sync.py:312-344`
- Model: `app/db/models/repository.py`
- Architecture doc: `docs/explanation/github-repository-ingestion.md`
- Related: [[wire-push-notifications-into-event-bus]]
