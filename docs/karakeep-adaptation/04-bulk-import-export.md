# Bulk Import/Export

**Status:** Missing (only per-summary PDF export exists)
**Complexity:** Medium
**Dependencies:** User Tags ([01-user-tags.md](01-user-tags.md)) for tag mapping during import

## Problem Statement

BSR can only export individual summaries as PDF. There is no way to import bookmarks from external services (Pocket, Raindrop, Omnivore, browser exports) or export all data in a portable format. Karakeep supports importing from 6+ formats and exporting to JSON/HTML.

## Import Formats

### Supported Sources

| Format | Source | File Type | Key Fields |
|--------|--------|-----------|------------|
| Netscape HTML | Browser bookmark export (Chrome, Firefox, Safari) | `.html` | URL, title, add_date, tags (via folders) |
| Pocket | Pocket export | `.html` / `.csv` | URL, title, tags, time_added |
| Omnivore | Omnivore export | `.json` | URL, title, labels, highlights, saved_at |
| Linkwarden | Linkwarden export | `.json` | URL, title, collection, tags, created_at |
| Karakeep | Karakeep export | `.json` | URL, title, tags, lists, note, created_at |
| Generic CSV | Any source | `.csv` | Columns: `url`, `title`, `tags` (comma-separated), `notes` |

### Parser Architecture

```
ImportFile
  -> FormatDetector.detect(file) -> format_type
    -> ParserFactory.get_parser(format_type)
      -> NetscapeHTMLParser / PocketParser / OmnivoreParser / ...
        -> List[ImportedBookmark]
```

Each parser produces a unified `ImportedBookmark` data class:

```python
@dataclass
class ImportedBookmark:
    url: str
    title: str | None = None
    tags: list[str] = field(default_factory=list)
    notes: str | None = None
    created_at: datetime | None = None
    collection_name: str | None = None  # for collection auto-creation
    highlights: list[dict] | None = None  # for Omnivore
    extra: dict = field(default_factory=dict)  # format-specific metadata
```

## Data Model

New models in `app/db/models.py`:

```python
class ImportJob(BaseModel):
    """Tracks a bulk import operation."""
    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="import_jobs", on_delete="CASCADE")
    source_format = peewee.TextField()          # netscape_html, pocket, omnivore, etc.
    file_name = peewee.TextField(null=True)
    status = peewee.TextField(default="pending")  # pending | processing | completed | failed
    total_items = peewee.IntegerField(default=0)
    processed_items = peewee.IntegerField(default=0)
    created_items = peewee.IntegerField(default=0)
    skipped_items = peewee.IntegerField(default=0)   # duplicates
    failed_items = peewee.IntegerField(default=0)
    errors_json = JSONField(default=list)            # [{url, error}]
    options_json = JSONField(default=dict)            # {summarize: bool, collection_id: int?}
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "import_jobs"
        indexes = (
            (("user",), False),
            (("status",), False),
        )
```

## Import Pipeline

### Flow

```
1. User uploads file via API or Telegram
2. FormatDetector identifies format
3. Parser extracts List[ImportedBookmark]
4. ImportJob created with total_items count
5. Background processing (APScheduler):
   a. For each ImportedBookmark:
      - Normalize URL, compute dedupe_hash
      - Skip if dedupe_hash exists (increment skipped_items)
      - Create Request record (type="import")
      - Create tags from bookmark.tags (using Tag model from 01-user-tags)
      - Optionally add to collection (auto-create from collection_name)
      - Optionally trigger summarization pipeline
      - Update ImportJob progress counters
   b. Set status="completed" when all items processed
```

### Options

Users can configure import behavior:

```json
{
    "summarize": true,         // run through LLM pipeline (default: false for speed)
    "create_tags": true,       // create Tag records from imported tags (default: true)
    "target_collection_id": 5, // add all imports to this collection (optional)
    "skip_duplicates": true    // skip URLs already in BSR (default: true)
}
```

### Deduplication

Import uses the same `dedupe_hash` (SHA-256 of normalized URL) as the regular pipeline. Already-existing URLs are skipped with a counter increment.

## Export Formats

| Format | Description | Content |
|--------|-------------|---------|
| JSON | Full BSR data export | Summaries + tags + collections + highlights + reading progress |
| CSV | Flat table export | URL, title, tags, language, created_at, is_read, is_favorited |
| Netscape HTML | Browser-importable bookmarks | URL, title, tags as folders |

### Export Payload (JSON)

```json
{
    "version": 1,
    "exported_at": "2026-03-21T10:30:00Z",
    "user_id": 123456789,
    "summaries": [
        {
            "url": "https://example.com/article",
            "title": "Article Title",
            "tags": ["tag1", "tag2"],
            "collections": ["Research"],
            "language": "en",
            "is_read": true,
            "is_favorited": false,
            "created_at": "2026-01-15T10:30:00Z",
            "summary_json": { ... },
            "highlights": [
                { "text": "highlighted text", "color": "yellow", "note": "my note" }
            ],
            "reading_progress": 0.75
        }
    ],
    "tags": [
        { "name": "tag1", "color": "#3B82F6" }
    ],
    "collections": [
        { "name": "Research", "description": "Research papers" }
    ]
}
```

## API Endpoints

Extend existing routers or create `app/api/routers/import_export.py`:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/import` | Upload import file. Multipart form: `file` + `options` JSON. Returns `ImportJob`. |
| `GET` | `/v1/import/{job_id}` | Get import job status and progress |
| `GET` | `/v1/import` | List user's import jobs |
| `DELETE` | `/v1/import/{job_id}` | Cancel/delete import job |
| `GET` | `/v1/export` | Stream export download. Query params: `format` (json\|csv\|html), `tag` (filter), `collection_id` (filter) |

### Import Response

```json
{
    "id": 42,
    "status": "processing",
    "source_format": "pocket",
    "total_items": 150,
    "processed_items": 73,
    "created_items": 65,
    "skipped_items": 8,
    "failed_items": 0
}
```

## Frontend (React + Carbon)

### New Components

- **ImportExportPage** (`web/src/features/import-export/ImportExportPage.tsx`) -- two sections:
  - **Import**: Carbon `FileUploader` with format auto-detection, options form, progress indicator
  - **Export**: format selector (Carbon `RadioButtonGroup`), optional filters, download button
- **ImportJobStatus** (`web/src/features/import-export/ImportJobStatus.tsx`) -- progress bar with counters (processed/created/skipped/failed)
- **ImportHistory** (`web/src/features/import-export/ImportHistory.tsx`) -- Carbon `DataTable` of past import jobs

### Route

Add `/web/import-export` route under settings/preferences section.

## Telegram Bot Integration

### Import via Telegram

- User sends a file (HTML, JSON, CSV) to the bot
- Bot detects it as an import file and asks for confirmation: "Found 150 bookmarks in Pocket format. Import? [Yes / Yes + Summarize / Cancel]"
- On confirmation, creates ImportJob and processes in background
- Sends progress updates: "Imported 73/150 (8 skipped as duplicates)"
- Sends completion message with summary stats

### Export via Telegram

- `/export [format]` -- generates export and sends as a file attachment
- Supported formats: `json`, `csv`, `html`
- Default: `json`

## Parser Implementation Notes

### Netscape HTML Parser

Standard `<DT><A HREF="..." ADD_DATE="..." TAGS="...">Title</A>` format. Use `html.parser` stdlib. Folder hierarchy (`<DL>` nesting) maps to collection names.

### Pocket Parser

Pocket exports as Netscape HTML with `tags` attribute on `<A>` elements. Time stored as Unix timestamp in `ADD_DATE`.

### Omnivore Parser

JSON array of objects with `url`, `title`, `labels[]`, `highlights[]`, `savedAt`. Labels map to tags. Highlights map to `SummaryHighlight` records.

### CSV Parser

Expect headers: `url` (required), `title`, `tags`, `notes`, `created_at`. Tags field is comma-separated within the column. Use Python's `csv.DictReader`.

## Testing

- Parser unit tests for each format (with fixture files in `tests/fixtures/`)
- Import pipeline integration test: upload file, verify Request/Tag/Collection records created
- Dedup test: import same file twice, verify skipped counts
- Export test: create test data, export each format, verify structure
- Telegram file handling test
