---
title: Replace bare Exception raises in orchestrator with typed PipelineStageError
status: backlog
area: llm
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Replace bare Exception raises in orchestrator with typed PipelineStageError #repo/ratatoskr #area/llm #status/backlog 🔼

## Objective

`app/agents/orchestrator.py:199,222,466` uses bare `raise Exception(...)` for pipeline stage failures. These are caught by the generic `except Exception as e` handler at line 397, making it impossible to distinguish network errors, extraction failures, and logic bugs. Diagnostic value is lost.

## Context

- `app/agents/orchestrator.py:199,222,466` — three bare raise sites
- `app/agents/orchestrator.py:397` — generic catch-all handler
- `app/agents/base_agent.py` — good reference for structured agent errors

## Acceptance criteria

- [ ] `PipelineStageError(RuntimeError)` defined with at least a `stage: str` field and optional `cause: Exception`
- [ ] All three raise sites updated to `raise PipelineStageError(stage="extraction", cause=e)`
- [ ] The catch-all handler catches `PipelineStageError` separately and logs `error.stage` for structured diagnostics
- [ ] Generic `Exception` catch remains as a fallback for truly unexpected errors

## Definition of done

A forced extraction failure produces a log entry with `stage=extraction` in the structured output.
