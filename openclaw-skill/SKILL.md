# Bite-Size Reader — Article Knowledge Base

## Description

Bite-Size Reader is a personal knowledge base of web article summaries. It ingests URLs, extracts content using Firecrawl, and generates structured summaries via LLM. This skill gives you access to search, browse, and retrieve article summaries from the database.

## Capabilities

- **Search articles** by keyword, topic tag, or entity name
- **Retrieve article details** including key ideas, entities, readability scores, and topic tags
- **Browse recent articles** with optional filtering by language, favorites, or tag
- **Read full article content** (original extracted markdown/text)
- **Get database statistics** including total articles, language breakdown, and top tags
- **Find articles by entity** (people, organizations, locations)

## Available Tools

### search_articles
Search stored article summaries by keyword, topic, or entity. Performs full-text search across titles, summaries, tags, and entities.

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Max results 1-25, default 10

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
