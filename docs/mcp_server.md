# MCP Server

Bite-Size Reader exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that allows external AI agents (OpenClaw, Claude Desktop, etc.) to search, retrieve, and explore stored article summaries.

## Configuration

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `MCP_ENABLED` | `false` | Enable the MCP server |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |
| `MCP_HOST` | `0.0.0.0` | SSE bind address |
| `MCP_PORT` | `8200` | SSE port |

See `docs/environment_variables.md` for full config reference.

## Running

**stdio mode** (default -- for OpenClaw / Claude Desktop):

```bash
python -m app.cli.mcp_server
```

**SSE mode** (HTTP-based integrations):

```bash
python -m app.cli.mcp_server --transport sse --port 8200
```

## Tools (12)

| Tool | Description |
| ------ | ------------- |
| `search_articles(query, limit)` | Full-text search across titles, summaries, tags, entities |
| `get_article(summary_id)` | Full summary details by ID |
| `list_articles(limit, offset, is_favorited, lang, tag)` | Paginated article list with filters |
| `get_article_content(summary_id)` | Original crawled content (markdown/text, capped at 50k chars) |
| `get_stats()` | Database statistics: counts, languages, top tags, request types |
| `find_by_entity(entity_name, entity_type, limit)` | Find articles mentioning a person, org, or location |
| `list_collections(limit, offset)` | List top-level article collections |
| `get_collection(collection_id, include_items, limit)` | Collection details with articles |
| `list_videos(limit, offset, status)` | List YouTube video downloads with metadata |
| `get_video_transcript(video_id)` | Video transcript text (capped at 50k chars) |
| `check_url(url)` | Check if a URL has already been processed (uses SHA-256 dedup) |
| `semantic_search(description, limit, language)` | Vector similarity search via ChromaDB (falls back to keyword) |

## Resources (10)

| URI | Description |
| ----- | ------------- |
| `bsr://articles/recent` | 10 most recent article summaries |
| `bsr://articles/favorites` | All favorited summaries |
| `bsr://articles/unread` | Up to 20 unread summaries |
| `bsr://stats` | Database statistics snapshot |
| `bsr://tags` | All topic tags with counts |
| `bsr://entities` | Aggregated people, organizations, locations |
| `bsr://domains` | Source domains with article counts |
| `bsr://collections` | Top-level collections with item counts |
| `bsr://videos/recent` | 10 most recent completed video downloads |
| `bsr://processing/stats` | LLM call counts, token usage, model breakdown, video stats |

## Graceful Degradation

- ChromaDB is optional. When unavailable, `semantic_search` falls back to keyword-based `search_articles`.
- The MCP server logs to stderr (required by stdio transport) and never writes to stdout outside of MCP protocol messages.

## Implementation

Source: `app/mcp/server.py`

The server uses [FastMCP](https://github.com/modelcontextprotocol/python-sdk) and connects to the same SQLite database as the main bot. Database is initialized once at startup via Peewee ORM.
