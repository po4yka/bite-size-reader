---
title: Migrate ConfigHelper to delegate to AppConfig instead of os.getenv directly
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Migrate ConfigHelper to delegate to AppConfig instead of os.getenv directly #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`ConfigHelper` / `Config` in `app/config/settings.py:459-528` reads `os.getenv()` directly, bypassing the validated `AppConfig` cache. Auth middleware and access control use this path. In tests, patching env vars and patching `AppConfig` are independent and can silently diverge — a test may patch `AppConfig` but the actual auth check reads the raw env var.

## Context

- `app/config/settings.py:459-528` — `Config.is_user_allowed()`, `get_allowed_user_ids()`, `get_allowed_client_ids()` all call `os.getenv()`
- `app/di/shared.py` — `AppConfig` is the validated, cached config object
- Auth middleware and `access_controller.py` are the primary callers

## Acceptance criteria

- [ ] `Config.is_user_allowed()` and `get_allowed_user_ids()` delegate to `load_config().telegram.allowed_user_ids`
- [ ] `Config.get_allowed_client_ids()` delegates to `load_config()` equivalent
- [ ] Tests patching `AppConfig` see consistent behavior in auth checks
- [ ] No remaining `os.getenv("ALLOWED_USER_IDS")` calls in auth-critical paths

## Definition of done

A test that patches `AppConfig.telegram.allowed_user_ids` and calls `Config.is_user_allowed()` sees the patched value.
