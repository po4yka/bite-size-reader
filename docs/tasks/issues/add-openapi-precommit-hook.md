---
title: Add generate:api to pre-commit hook so OpenAPI types are always current on commit
status: backlog
area: ci
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add generate:api to pre-commit hook so OpenAPI types are always current on commit #repo/ratatoskr #area/ci #status/backlog 🔽

## Objective

`clients/web/src/api/generated.ts` is regenerated only in CI (`web-static-check` job). Drift accumulates between PRs when the OpenAPI spec changes and the generated types are not updated before commit. Adding `npm run generate:api` to the pre-commit hook ensures `generated.ts` is always current.

## Context

- `.pre-commit-config.yaml` — current hooks: ruff, isort, mypy, pre-commit-hooks, markdownlint, class/file LOC limits
- `clients/web/package.json` — `generate:api` script: `openapi-typescript docs/openapi/mobile_api.yaml -o src/api/generated.ts`

## Acceptance criteria

- [ ] A new `local` pre-commit hook runs `cd clients/web && npm run generate:api` when `docs/openapi/mobile_api.yaml` changes
- [ ] The hook stages the updated `generated.ts` automatically if it changes
- [ ] Hook only runs when the OpenAPI YAML is in the commit's changed file list (use `files:` filter)

## Definition of done

Modifying `mobile_api.yaml` and running `pre-commit run` regenerates `generated.ts` automatically.
