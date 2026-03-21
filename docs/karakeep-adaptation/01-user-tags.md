# User Tagging System

**Status:** Missing
**Complexity:** Medium
**Dependencies:** None (foundation for Rule Engine, Import/Export, Browser Extension)

## Problem Statement

BSR only has LLM-generated `topic_tags` baked into the summary JSON payload. Users cannot manually tag, rename, merge, or filter by their own taxonomy. Karakeep supports both manual and AI-generated tags as first-class entities with full CRUD, merge, and search integration.

## Design Goals

- Users can create, rename, delete, and merge tags
- Tags can be attached to summaries manually or by AI
- AI-generated `topic_tags` from the summary contract are backfilled as `source="ai"` tags
- Tags are searchable and filterable across all views
- Tags integrate with the existing sync protocol (`server_version`)

## Data Model

New models in `app/db/models.py`:

```python
class Tag(BaseModel):
    """User-defined tag for organizing summaries."""
    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="tags", on_delete="CASCADE")
    name = peewee.TextField()
    normalized_name = peewee.TextField()  # lowercased, stripped for dedup
    color = peewee.TextField(null=True)   # hex color for UI display
    server_version = peewee.BigIntegerField(default=_next_server_version)
    is_deleted = peewee.BooleanField(default=False)
    deleted_at = peewee.DateTimeField(null=True)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "tags"
        indexes = (
            (("user", "normalized_name"), True),  # unique per user
        )


class SummaryTag(BaseModel):
    """Association between a Summary and a Tag."""
    id = peewee.AutoField()
    summary = peewee.ForeignKeyField(Summary, backref="summary_tags", on_delete="CASCADE")
    tag = peewee.ForeignKeyField(Tag, backref="summary_tags", on_delete="CASCADE")
    source = peewee.TextField(default="manual")  # "manual" | "ai" | "rule" | "import"
    server_version = peewee.BigIntegerField(default=_next_server_version)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "summary_tags"
        indexes = (
            (("summary", "tag"), True),  # unique pair
            (("tag",), False),           # fast tag-based lookups
        )
```

### Migration Plan

1. Create `tags` and `summary_tags` tables
2. Backfill: for each existing summary, extract `topic_tags` from `json_payload`, create `Tag` rows (deduped by `normalized_name` per user), create `SummaryTag` rows with `source="ai"`
3. Going forward, the summarization pipeline creates `SummaryTag` rows alongside writing `topic_tags` into the JSON payload

## API Endpoints

New router: `app/api/routers/tags.py`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/tags` | List user's tags with summary counts. Query params: `q` (search), `sort` (name\|count\|created_at) |
| `POST` | `/v1/tags` | Create a tag. Body: `{ name, color? }` |
| `GET` | `/v1/tags/{tag_id}` | Get tag details with summary count |
| `PATCH` | `/v1/tags/{tag_id}` | Update tag name/color |
| `DELETE` | `/v1/tags/{tag_id}` | Soft-delete tag (cascades to SummaryTag rows) |
| `POST` | `/v1/tags/merge` | Merge tags. Body: `{ source_tag_ids: [], target_tag_id }` |
| `POST` | `/v1/summaries/{summary_id}/tags` | Attach tag(s). Body: `{ tag_ids: [] }` or `{ tag_names: [] }` (auto-create) |
| `DELETE` | `/v1/summaries/{summary_id}/tags/{tag_id}` | Detach tag from summary |

Extend existing `GET /v1/summaries` with query param `tag` (filter by tag name or ID).

### Response Schemas

```python
# Tag list item
{
    "id": 1,
    "name": "machine-learning",
    "color": "#3B82F6",
    "summary_count": 42,
    "source_breakdown": { "manual": 10, "ai": 32 },
    "created_at": "2026-01-15T10:30:00Z"
}

# Summary with tags (extend existing response)
{
    "id": "abc-123",
    "title": "...",
    "tags": [
        { "id": 1, "name": "machine-learning", "color": "#3B82F6", "source": "ai" },
        { "id": 5, "name": "important", "color": "#EF4444", "source": "manual" }
    ]
}
```

## Domain Layer

New files:

- `app/domain/models/tag.py` -- `Tag` and `SummaryTag` domain models
- `app/domain/services/tag_service.py` -- business logic (create, merge, normalize)
- `app/application/use_cases/tag_management.py` -- orchestration

### Tag Normalization

```python
def normalize_tag_name(name: str) -> str:
    """Lowercase, strip whitespace, collapse internal spaces."""
    return " ".join(name.lower().strip().split())
```

Prevents duplicates like "Machine Learning" vs "machine learning" vs " machine learning ".

### Merge Logic

When merging tags A, B into target C:

1. Re-point all `SummaryTag` rows from A/B to C (skip if C already attached to that summary)
2. Soft-delete tags A and B
3. Emit `tag.merged` event on EventBus

## Frontend (React + Carbon)

### New Components

- **TagManagementPage** (`web/src/features/tags/TagManagementPage.tsx`) -- CRUD list with Carbon `DataTable`, inline edit, color picker, merge action
- **TagPills** (`web/src/components/TagPills.tsx`) -- reusable tag display (colored pills with remove button)
- **TagPicker** (`web/src/components/TagPicker.tsx`) -- Carbon `MultiSelect` / `ComboBox` for attaching tags, with auto-create option
- **TagFilter** (`web/src/components/TagFilter.tsx`) -- sidebar filter for library/search views

### Integration Points

- **Library page** -- add tag filter to sidebar, show tag pills on article cards
- **Article detail page** -- show tags section with TagPicker for editing
- **Search page** -- support `tag:name` query syntax

### Route

Add `/web/tags` route for tag management page.

## Telegram Bot Integration

### Commands

- `/tag <name>` (reply to summary message) -- attach tag to the replied summary. Auto-creates tag if it does not exist.
- `/untag <name>` (reply to summary message) -- detach tag
- `/tags` -- list all user tags with counts
- `/tags <name>` -- show summaries with that tag (paginated)

### Inline Keyboard

After summary delivery, add a "Tag" button to the inline keyboard. When pressed, show a list of the user's most-used tags (max 8) as inline buttons, plus a "New tag..." option that prompts for text input.

## Search Integration

### FTS5

Extend `TopicSearchIndex` to include user tags in the `tags` field. When a `SummaryTag` is added/removed, update the FTS5 index entry for that summary.

### ChromaDB

Add user tags as metadata on the ChromaDB document. This allows filtering semantic search results by tag.

### Query Syntax

Support `tag:machine-learning` in the search query parser. This filters results to summaries with that tag attached.

## Sync Protocol

Tags and SummaryTags are sync-aware via `server_version`. Delta sync includes:

- New/updated/deleted tags since last sync version
- New/deleted SummaryTag associations since last sync version

Extend `app/api/routers/sync.py` delta response to include `tags` and `summary_tags` arrays.

## Event Bus Integration

Emit events for rule engine and webhook integration:

- `tag.created` -- when a new tag is created
- `tag.attached` -- when a tag is attached to a summary (includes `source`)
- `tag.detached` -- when a tag is removed from a summary
- `tag.merged` -- when tags are merged
- `tag.deleted` -- when a tag is deleted

## Testing

- Unit tests for tag normalization, merge logic, dedup
- API integration tests for all CRUD endpoints
- Migration test: verify backfill from existing `topic_tags`
- Telegram command tests for `/tag` and `/untag`
