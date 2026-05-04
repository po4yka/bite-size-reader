---
title: Replace bespoke retry loops in OpenRouter and Firecrawl adapters with tenacity
status: backlog
area: llm
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Replace bespoke retry loops in OpenRouter and Firecrawl adapters with tenacity #repo/ratatoskr #area/llm #status/backlog 🔼

## Objective

OpenRouter and Firecrawl adapters both implement manual exponential backoff retry loops (~60 lines each of bespoke logic). Using `tenacity` reduces this to a declarative `@retry` decorator, eliminates retry logic drift between adapters, and provides built-in jitter, `stop_after_attempt`, and `wait_exponential`.

## Context

- `app/adapters/openrouter/` — error handler + retry in `chat_attempt_runner.py`
- `app/adapters/content/content_extractor.py` — Firecrawl retry logic
- `tenacity` is not currently in `pyproject.toml` dependencies

## Acceptance criteria

- [ ] `tenacity` added to core dependencies in `pyproject.toml`
- [ ] OpenRouter retry logic replaced with `@retry(wait=wait_exponential(...), stop=stop_after_attempt(...), retry=retry_if_exception_type(...))`
- [ ] Firecrawl retry logic replaced similarly
- [ ] Retry counts and backoff parameters are configurable via `AppConfig`, not hardcoded in the decorator
- [ ] Existing tests for retry behavior pass unchanged

## Definition of done

`rg 'for.*attempt\|while.*retry' app/adapters/openrouter/ app/adapters/content/` returns zero manual retry loops.
