---
name: langgraph-summarize-loop
description: Debug the LangGraph summarize/validate/repair retry loop and LLM attempt trail. Trigger keywords -- LangGraph, retry, repair loop, attempt_trigger, attempt_index, stream fallback, validation failure, self-correction, summarization agent.
version: 1.0.0
allowed-tools: Bash, Read, Grep
---

# LangGraph Summarize Loop

Trace and debug the LangGraph-based summarize/validate/repair retry graph that wraps every LLM summarization call.

## The Attempt Trail

Every LLM invocation lands in `llm_calls` with two queryable fields:

| Column | Meaning |
| ------ | ------- |
| `attempt_index` | 1-based monotonic counter per `request_id` |
| `attempt_trigger` | Postgres enum (see below) |

### `attempt_trigger` values

| Value | Meaning |
| ----- | ------- |
| `initial` | First call on a fresh request |
| `user_retry` | User asked for another pass (e.g. `/redo`) |
| `auto_backfill` | Background job filling a missing summary |
| `repair_loop` | Validation failed -- graph re-prompts with the error |
| `stream_fallback_retry` | Streaming attempt failed; non-streaming retry |

A healthy summarization for a hard URL might look like:
`initial -> repair_loop -> repair_loop` (3 rows, attempt_index 1..3, status `ok` on the last).

A pathological one: `initial -> repair_loop -> repair_loop -> repair_loop` with all errors -- the graph hit its retry budget.

## Dynamic Context

```bash
!docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -t -c "SELECT attempt_trigger, count(*) FROM llm_calls WHERE created_at > now() - interval '24 hours' GROUP BY attempt_trigger ORDER BY count DESC"
```

## Common Queries

### Full attempt trail for a request

```bash
docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -c \
  "SELECT attempt_index, attempt_trigger, model, status,
          tokens_prompt, tokens_completion, cost_usd,
          left(error_text, 80) AS err_preview, created_at
     FROM llm_calls
    WHERE request_id = (SELECT id FROM requests WHERE correlation_id = '<correlation_id>')
    ORDER BY attempt_index;"
```

### Requests that exhausted the repair loop

```bash
docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -c \
  "SELECT r.correlation_id, r.input_url, count(*) AS attempts
     FROM llm_calls l JOIN requests r ON r.id = l.request_id
    WHERE l.attempt_trigger = 'repair_loop'
      AND l.created_at > now() - interval '24 hours'
    GROUP BY r.correlation_id, r.input_url
   HAVING count(*) >= 3
    ORDER BY attempts DESC LIMIT 20;"
```

### Streaming fallback rate

```bash
docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -c \
  "SELECT date_trunc('hour', created_at) AS hr,
          count(*) FILTER (WHERE attempt_trigger = 'stream_fallback_retry') AS stream_fallbacks,
          count(*) AS total
     FROM llm_calls
    WHERE created_at > now() - interval '24 hours'
    GROUP BY hr ORDER BY hr DESC;"
```

### What did the validator reject?

```bash
docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -At -c \
  "SELECT error_text
     FROM llm_calls
    WHERE attempt_trigger = 'repair_loop'
      AND request_id = (SELECT id FROM requests WHERE correlation_id = '<correlation_id>')
    ORDER BY attempt_index;"
```

The repair-loop error_text contains the validator feedback that's fed back into the next prompt.

### View the prompt sent on a specific attempt

```bash
docker exec -i ratatoskr-postgres psql -U ratatoskr_app -d ratatoskr -At -c \
  "SELECT request_messages_json
     FROM llm_calls
    WHERE request_id = (SELECT id FROM requests WHERE correlation_id = '<correlation_id>')
      AND attempt_index = <n>;" \
  | python -m json.tool
```

## Graph Structure

The retry graph is defined in `app/agents/langgraph/graph.py`. Nodes (typical):

- `summarize` -- structured-output call against OpenRouter
- `validate` -- runs `app/core/summary_contract.py` against the JSON
- `repair` -- re-prompts with the validator's error message
- Edges loop `summarize -> validate -> (ok | repair -> summarize)` up to a budget

Budget is configured in the agent config; default ~3 repair iterations. Beyond that the graph emits a hard error rather than retrying forever.

## Key Files

- **Graph**: `app/agents/langgraph/graph.py`
- **Summarization agent**: `app/agents/summarization_agent.py`
- **Validation**: `app/core/summary_contract.py`, `app/core/summary_schema.py`
- **JSON repair**: `app/core/json_utils.py` (cheap pre-validation fix)
- **LLM client**: `app/adapters/llm/`, `app/adapters/openrouter/openrouter_client.py`
- **DB table**: `llm_calls`
- **Architecture doc**: `docs/explanation/multi-agent-architecture.md`

## Important Notes

- `attempt_trigger` is a Postgres enum -- if you add a new value, you need a migration that ALTERs the type (see the `alembic-migrations` skill).
- The graph persists checkpoints; resuming a partially-failed request reuses the prior state.
- Stream fallback retries don't reset `attempt_index` -- they're additional rows continuing the same counter.
- `LLM_CALL_TIMEOUT_SEC` is the OUTER cascade budget. `LLM_PER_MODEL_TIMEOUT_MIN_SEC` is the floor per model. Models in `LLM_PER_MODEL_TIMEOUT_OVERRIDES` get longer floors.
- Cost reconciliation: `tokens_prompt` + `tokens_completion` + `cost_usd` are persisted on every row including failed attempts.
- Update both `app/prompts/summary_system_en.txt` AND `app/prompts/summary_system_ru.txt` when changing prompt behavior -- the graph reads whichever matches `requests.lang_detected`.
