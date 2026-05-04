---
title: Add SAFETY_API_KEY secret to CI for Safety v3+ CVE scanning
status: backlog
area: ci
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add SAFETY_API_KEY secret to CI for Safety v3+ CVE scanning #repo/ratatoskr #area/ci #status/backlog ⏫

## Objective

Safety CLI v3+ requires an API key (`SAFETY_API_KEY`) to fetch CVE data. Without it the `safety check` step in CI either errors silently or returns incomplete results. Dependency vulnerability scanning is currently degraded.

## Context

- `.github/workflows/ci.yml` — `safety-scan` job runs `safety check --full-report` with no API key configured
- Safety v3+ free tier requires account registration at safety.pyup.io

## Acceptance criteria

- [ ] `SAFETY_API_KEY` secret added to the repository settings
- [ ] `safety-scan` job passes with a full CVE report
- [ ] If Safety is replaced with `pip-audit` exclusively, document the decision and remove the `safety check` step

## Definition of done

`safety-scan` CI job produces a non-empty vulnerability report or explicit "no known vulnerabilities" output.
