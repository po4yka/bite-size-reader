# Rule Engine (Automation)

**Status:** Missing
**Complexity:** Large
**Dependencies:** User Tags ([01-user-tags.md](01-user-tags.md)), Per-User Webhooks ([03-per-user-webhooks.md](03-per-user-webhooks.md)), EventBus

## Problem Statement

BSR has no way to automate actions on content. Users must manually tag, archive, or organize every summary. Karakeep provides an event-condition-action rule engine that automates organization based on content properties.

## Design Goals

- Users define rules: "when X happens, if Y is true, do Z"
- Rules trigger on domain events via the existing EventBus (`app/infrastructure/messaging/`)
- Conditions evaluate summary properties (domain, tags, language, reading time)
- Actions modify summaries (tag, archive, add to collection, send webhook)
- Rules execute asynchronously and non-blocking to the main pipeline
- Execution history is logged for debugging

## Data Model

New models in `app/db/models.py`:

```python
class AutomationRule(BaseModel):
    """User-defined automation rule (event -> condition -> action)."""
    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="rules", on_delete="CASCADE")
    name = peewee.TextField()
    description = peewee.TextField(null=True)
    enabled = peewee.BooleanField(default=True)
    event_type = peewee.TextField()            # e.g. "summary.created"
    conditions_json = JSONField(default=list)   # [{type, field, operator, value}]
    actions_json = JSONField(default=list)       # [{type, params}]
    priority = peewee.IntegerField(default=0)   # lower = runs first
    run_count = peewee.IntegerField(default=0)
    last_triggered_at = peewee.DateTimeField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "automation_rules"
        indexes = (
            (("user", "enabled"), False),
            (("event_type",), False),
        )


class RuleExecutionLog(BaseModel):
    """Audit trail for rule executions."""
    id = peewee.AutoField()
    rule = peewee.ForeignKeyField(AutomationRule, backref="logs", on_delete="CASCADE")
    summary = peewee.ForeignKeyField(Summary, null=True, on_delete="SET NULL")
    event_type = peewee.TextField()
    matched = peewee.BooleanField()
    conditions_result_json = JSONField(null=True)  # per-condition pass/fail detail
    actions_taken_json = JSONField(null=True)       # actions executed + results
    error = peewee.TextField(null=True)
    duration_ms = peewee.IntegerField(null=True)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "rule_execution_logs"
        indexes = (
            (("rule",), False),
            (("created_at",), False),
        )
```

## Event Types

Leveraging the existing EventBus in `app/infrastructure/messaging/`:

| Event | Fires When |
|-------|-----------|
| `summary.created` | New summary is persisted |
| `summary.updated` | Summary metadata changes (read, favorite, etc.) |
| `request.completed` | Summarization pipeline finishes successfully |
| `request.failed` | Summarization pipeline fails |
| `tag.attached` | A tag is attached to a summary |
| `tag.detached` | A tag is removed from a summary |
| `collection.item_added` | A summary is added to a collection |

## Condition Types

Each condition evaluates a property of the summary or its source:

| Condition Type | Field | Operators | Example |
|---------------|-------|-----------|---------|
| `domain_matches` | `request.normalized_url` | `equals`, `contains`, `regex` | `domain_matches("arxiv.org")` |
| `title_contains` | `summary.json_payload.title` | `contains`, `regex` | `title_contains("AI")` |
| `has_tag` | `summary.tags` | `any`, `all`, `none` | `has_tag(["machine-learning"])` |
| `language_is` | `summary.lang` | `equals`, `in` | `language_is("ru")` |
| `reading_time` | `summary.json_payload.estimated_reading_time_min` | `gt`, `lt`, `eq` | `reading_time(gt=15)` |
| `source_type` | `summary.json_payload.source_type` | `equals`, `in` | `source_type("research_paper")` |
| `content_contains` | `summary.json_payload.summary_1000` | `contains`, `regex` | `content_contains("kubernetes")` |

Conditions combine with AND logic by default. Support `match_mode: "any"` for OR logic.

```json
{
    "conditions": [
        {"type": "domain_matches", "value": "arxiv.org", "operator": "contains"},
        {"type": "language_is", "value": "en", "operator": "equals"}
    ],
    "match_mode": "all"
}
```

## Action Types

| Action Type | Parameters | Effect |
|-------------|-----------|--------|
| `add_tag` | `{ tag_name: str }` | Attach tag (auto-create if missing). Sets `source="rule"`. |
| `remove_tag` | `{ tag_name: str }` | Detach tag from summary |
| `add_to_collection` | `{ collection_id: int }` | Add summary to collection |
| `remove_from_collection` | `{ collection_id: int }` | Remove summary from collection |
| `archive` | `{}` | Set `is_deleted=True` on summary |
| `set_favorite` | `{ value: bool }` | Set `is_favorited` flag |
| `send_webhook` | `{ url: str }` | POST summary data to URL (one-off, not managed webhook) |

Multiple actions per rule. Executed in order.

```json
{
    "actions": [
        {"type": "add_tag", "params": {"tag_name": "research"}},
        {"type": "add_to_collection", "params": {"collection_id": 5}},
        {"type": "set_favorite", "params": {"value": true}}
    ]
}
```

## Architecture

### Execution Flow

```
EventBus event
  -> RuleEngineSubscriber.on_event(event)
    -> Load user's enabled rules matching event_type (ordered by priority)
    -> For each rule:
      -> Evaluate conditions against event payload
      -> If all/any conditions match:
        -> Execute actions in order
        -> Log execution to RuleExecutionLog
      -> If conditions don't match:
        -> Log skip to RuleExecutionLog (matched=False)
    -> Handle errors per-rule (don't abort remaining rules)
```

### Key Files

- `app/domain/services/rule_engine.py` -- condition evaluation, action dispatch
- `app/application/use_cases/rule_execution.py` -- orchestration, logging
- `app/infrastructure/messaging/handlers/rule_engine_handler.py` -- EventBus subscriber
- `app/api/routers/rules.py` -- API router

### Guardrails

- Max 50 rules per user
- Max 10 actions per rule
- Max 5 conditions per rule
- Execution timeout: 10 seconds per rule
- Loop detection: if an action triggers an event that re-triggers the same rule, skip re-execution (use a `processing_rule_ids` set per event chain)
- Rate limit: max 100 rule executions per minute per user

## API Endpoints

New router: `app/api/routers/rules.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/rules` | List user's rules |
| `POST` | `/v1/rules` | Create rule. Body: `{ name, event_type, conditions, actions, priority? }` |
| `GET` | `/v1/rules/{rule_id}` | Get rule details |
| `PATCH` | `/v1/rules/{rule_id}` | Update rule |
| `DELETE` | `/v1/rules/{rule_id}` | Soft-delete rule |
| `POST` | `/v1/rules/{rule_id}/test` | Dry-run rule against a summary ID. Returns what would match/execute. |
| `GET` | `/v1/rules/{rule_id}/logs` | Paginated execution history |

### Validation

Validate `event_type`, condition types, action types against known enums at creation time. Return `422` for unknown types.

## Frontend (React + Carbon)

### New Components

- **RulesPage** (`web/src/features/rules/RulesPage.tsx`) -- list of rules with enable/disable toggle, delete, edit
- **RuleEditor** (`web/src/features/rules/RuleEditor.tsx`) -- form with:
  - Name + description fields
  - Event type dropdown (Carbon `Select`)
  - Condition builder: dynamic rows with type/operator/value (Carbon `StructuredList` + form fields)
  - Action builder: ordered list with type-specific parameter forms
  - Priority field
  - Test button (run against a selected summary)
- **RuleLogViewer** (`web/src/features/rules/RuleLogViewer.tsx`) -- Carbon `DataTable` showing execution history

### Route

Add `/web/rules` route.

## Telegram Bot Integration

Rule management is too complex for chat UX. Telegram provides:

- `/rules` -- list enabled rules with names and run counts
- `/rules <id>` -- show rule details (conditions, actions, last triggered)
- Rule creation/editing -- redirect to web UI

Notifications: optionally notify via Telegram when a rule fires (configurable per rule).

## Testing

- Unit tests for condition evaluation logic (each condition type)
- Unit tests for action execution (each action type)
- Integration test: create rule via API, trigger event, verify action executed
- Loop detection test: verify rules don't cascade infinitely
- Dry-run test: verify `/test` endpoint returns expected results without side effects
