---
title: Set asyncio_mode = auto in pytest config to prevent silent vacuous async tests
status: backlog
area: testing
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Set asyncio_mode = auto in pytest config to prevent silent vacuous async tests #repo/ratatoskr #area/testing #status/backlog ⏫

## Objective

`pyproject.toml` sets `asyncio_default_fixture_loop_scope = "function"` but not `asyncio_mode`. Without `asyncio_mode = "auto"`, any async test function missing `@pytest.mark.asyncio` is collected by pytest but not awaited — it passes vacuously by returning a truthy coroutine object. This means broken async tests can silently pass CI.

## Context

- `pyproject.toml` — `[tool.pytest.ini_options]` section, line ~296
- Affects all `async def test_*` functions across `tests/`

## Acceptance criteria

- [ ] `asyncio_mode = "auto"` added to `[tool.pytest.ini_options]` in `pyproject.toml`
- [ ] All async tests that were previously passing vacuously are identified and fixed (add `@pytest.mark.asyncio` if needed, or verify they actually pass with the new mode)
- [ ] CI passes after the change

## Definition of done

`pytest --co -q` shows no warnings about unawaited coroutines; test count does not change unexpectedly.
