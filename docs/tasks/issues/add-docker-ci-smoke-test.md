---
title: Add Docker image build smoke test to CI (build but do not push on PRs)
status: backlog
area: ops
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add Docker image build smoke test to CI (build but do not push on PRs) #repo/ratatoskr #area/ops #status/backlog 🔽

## Objective

No CI job builds the Docker image on PRs. A Dockerfile or dependency change that breaks the build is only discovered at release time. A build-only smoke test catches these regressions early without publishing an image.

## Context

- `.github/workflows/ci.yml` — no Docker build job
- `.github/workflows/release.yml` — builds and pushes image only on version tags
- `ops/docker/Dockerfile` — multi-stage build, moderately complex

## Acceptance criteria

- [ ] New CI job builds `ops/docker/Dockerfile` with `docker build` (no push) on every PR
- [ ] Build uses layer caching via `cache-from: type=gha`
- [ ] Job is skipped on pushes to `main` if only non-Docker files changed (use `paths:` filter)
- [ ] Build failure blocks PR merge

## Definition of done

A syntax error introduced to the Dockerfile causes the CI job to fail before the PR can be merged.
