---
title: Progressively simplify JSON schema before binary structured-output downgrade
status: backlog
area: llm
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

- [ ] #task Progressively simplify JSON schema before binary structured-output downgrade #repo/ratatoskr #area/llm #status/backlog 🔽

## Problem

`error_handler.should_downgrade_response_format` currently performs a binary downgrade: `json_schema → json_object → off` on the first 400 that mentions `response_format` in the error body. Some providers reject specific schema constructs (`additionalProperties: false`, deeply nested `oneOf`, `$defs` references) rather than rejecting structured output entirely. The binary flip discards the schema completely, losing field-level validation for the remaining retry attempts. A progressive simplifier that strips strict-mode features one step at a time would preserve as much structure as possible before falling back to unstructured JSON.

## Proposed approach

- Create `app/adapters/openrouter/schema_simplifier.py` with a `simplify_schema` function that applies a sequence of transformations to a JSON Schema dict: (1) remove `additionalProperties: false` at all levels, (2) unwrap `oneOf`/`anyOf` with a single branch, (3) flatten `$defs` inline, (4) remove `required` constraints, (5) strip all constraints leaving bare type hints.
- Each simplification step produces a new schema; the caller retries with each in sequence before triggering the existing `json_object` → off downgrade path.
- Detect schema-induced 400 vs other 400s by checking `error_handler.should_downgrade_response_format` — extend its return to include a `schema_simplifiable` flag when the error text implies a schema construct rejection.
- Wire `schema_simplifier` into `error_handler.py` so the retry loop in `openrouter_client.py` consumes simplification steps transparently.
- Add unit tests for each simplification transform and integration tests confirming no regression on the binary downgrade path.

## Open questions

- In what order should constructs be stripped? `additionalProperties: false` is the most common offender — should it be step 1? Does stripping it before unwrapping `oneOf` cause parse ambiguity for some providers?
- How to reliably distinguish schema-induced 400 vs other semantic 400s (e.g. content policy)? The current error text check (`"response_format" in err_dump`) may match both.
- Should simplified schemas be cached by content hash to avoid re-computing on every retry within a single request?

## Files to touch

- `app/adapters/openrouter/schema_simplifier.py` (new)
- `app/adapters/openrouter/error_handler.py`
- `app/adapters/openrouter/openrouter_client.py`
- `tests/test_schema_simplifier.py` (new)
