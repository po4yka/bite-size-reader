# Bite-Size Reader — Article Knowledge Base

## Description

Bite-Size Reader is a personal knowledge base of web article summaries. It ingests URLs, extracts content using Firecrawl, and generates structured summaries via LLM. It also downloads YouTube videos and extracts transcripts. This skill gives you access to search, browse, and retrieve article summaries, manage collections, explore video transcripts, and check URL processing status.

## Capabilities

- **Search articles** by keyword, topic tag, or entity name (full-text search)
- **Semantic search** by natural-language description using ChromaDB vector embeddings
- **Retrieve article details** including key ideas, entities, readability scores, and topic tags
- **Browse recent articles** with optional filtering by language, favorites, or tag
- **Read full article content** (original extracted markdown/text)
- **Get database statistics** including total articles, language breakdown, and top tags
- **Find articles by entity** (people, organizations, locations)
- **Manage collections** — browse and inspect reading lists / article folders
- **Access YouTube videos** — list downloads, read transcripts
- **Check URL status** — verify if a URL has already been processed (deduplication)
- **Explore tags, entities, source domains, and processing stats** via discoverable resources

## Available Tools

### search_articles

Search stored article summaries by keyword, topic, or entity. Performs full-text search (FTS5) across titles, summaries, tags, and entities.

**Parameters:**

- `query` (string, required): Search query
- `limit` (integer, optional): Max results 1-25, default 10

### semantic_search

Search articles by meaning using ChromaDB vector similarity. Finds articles whose content is semantically similar to your description, even when exact keywords don't match. Falls back to keyword search if ChromaDB is unavailable.

**Parameters:**

- `description` (string, required): Natural-language description of what you're looking for
- `limit` (integer, optional): Max results 1-25, default 10
- `language` (string, optional): Language filter (e.g. "en", "ru"). Auto-detected if omitted.

### get_article

Get full details of a specific article summary by its numeric ID. Returns key ideas, entities, topic tags, reading time, readability score, and more.

**Parameters:**

- `summary_id` (integer, required): The summary ID

### list_articles

List stored articles with optional filters, sorted most-recent first.

**Parameters:**

- `limit` (integer, optional): 1-100, default 20
- `offset` (integer, optional): Pagination offset, default 0
- `is_favorited` (boolean, optional): Filter favorites
- `lang` (string, optional): Language code filter (e.g. "en", "ru")
- `tag` (string, optional): Topic tag filter (e.g. "#ai")

### get_article_content

Get the full extracted content (markdown/text) used to generate a summary. Useful for reading the complete article.

**Parameters:**

- `summary_id` (integer, required): The summary ID

### get_stats

Get database statistics: total articles, unread count, favorites, language breakdown, top tags, and request type counts.

### find_by_entity

Find articles mentioning a specific entity (person, organization, or location).

**Parameters:**

- `entity_name` (string, required): Entity to search for
- `entity_type` (string, optional): "people", "organizations", or "locations"
- `limit` (integer, optional): Max results 1-25, default 10

### list_collections

List article collections (folders / reading lists). Returns top-level collections with item counts and child collection counts.

**Parameters:**

- `limit` (integer, optional): 1-50, default 20
- `offset` (integer, optional): Pagination offset, default 0

### get_collection

Get details of a specific collection including its article summaries and child collections.

**Parameters:**

- `collection_id` (integer, required): The collection ID
- `include_items` (boolean, optional): Include article summaries (default true)
- `limit` (integer, optional): Max articles to include 1-100, default 50

### list_videos

List downloaded YouTube videos with metadata (title, channel, duration, transcript availability).

**Parameters:**

- `limit` (integer, optional): 1-50, default 20
- `offset` (integer, optional): Pagination offset, default 0
- `status` (string, optional): Filter by status: "completed", "pending", "error"

### get_video_transcript

Get the transcript text of a YouTube video by its video ID.

**Parameters:**

- `video_id` (string, required): YouTube video ID (e.g. "dQw4w9WgXcQ")

### check_url

Check whether a URL has already been processed and summarised. Uses the same normalisation and SHA-256 deduplication as the main pipeline.

**Parameters:**

- `url` (string, required): The URL to check

## Available Resources

| URI | Description |
| --- | --- |
| `bsr://articles/recent` | 10 most recent article summaries |
| `bsr://articles/favorites` | All favorited articles (up to 50) |
| `bsr://articles/unread` | Unread articles (up to 20) |
| `bsr://stats` | Database statistics (totals, languages, top tags) |
| `bsr://tags` | All topic tags with article counts |
| `bsr://entities` | Aggregated people, organizations, locations |
| `bsr://domains` | Source domains with article counts |
| `bsr://collections` | All top-level collections with item counts |
| `bsr://videos/recent` | 10 most recent completed video downloads |
| `bsr://processing/stats` | Processing statistics: LLM calls, token usage, costs, models |

## Data Model

Each article summary contains:

- **summary_250**: Short summary (max 250 chars)
- **summary_1000**: Extended summary (max 1000 chars)
- **tldr**: Concise multi-sentence summary
- **key_ideas**: 5 main ideas from the article
- **topic_tags**: Hashtag topics (e.g. #ai, #climate)
- **entities**: Extracted people, organizations, locations
- **estimated_reading_time_min**: Reading time estimate
- **key_stats**: Notable statistics with labels, values, units
- **answered_questions**: Questions the article answers
- **readability**: Flesch-Kincaid readability score and level
- **seo_keywords**: SEO-relevant keywords

Each video download contains:

- **video_id**: YouTube video identifier
- **title / channel**: Video and channel names
- **duration_sec**: Video duration in seconds
- **resolution**: Download quality (e.g. "1080p")
- **view_count / like_count**: Engagement metrics
- **transcript_text**: Cached transcript (if available)
- **transcript_source**: How transcript was obtained ("youtube-transcript-api" or "vtt")

## Setup

### stdio transport (recommended for OpenClaw)

```json
{
  "mcpServers": {
    "bite-size-reader": {
      "command": "python",
      "args": ["-m", "app.cli.mcp_server"],
      "cwd": "/path/to/bite-size-reader",
      "env": {
        "DB_PATH": "/data/app.db"
      }
    }
  }
}
```

### SSE transport (HTTP-based)

```bash
python -m app.cli.mcp_server --transport sse --port 8200
```

Then configure the MCP client to connect to `http://localhost:8200/sse`.

### Semantic search (requires ChromaDB)

For `semantic_search` to work, ChromaDB must be running and configured:

```bash
# Environment variables for ChromaDB
CHROMA_HOST=http://localhost:8000
CHROMA_AUTH_TOKEN=your-chroma-token  # optional
CHROMA_ENVIRONMENT=production
CHROMA_USER_SCOPE=public
```

If ChromaDB is not available, `semantic_search` automatically falls back to keyword search.
