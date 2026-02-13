# MCP Server

Bite-Size Reader exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that allows external AI agents (OpenClaw, Claude Desktop, etc.) to search, retrieve, and explore stored article summaries.

## Configuration

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `MCP_ENABLED` | `false` | Enable the MCP server |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio` or `sse` |
| `MCP_HOST` | `127.0.0.1` | SSE bind address |
| `MCP_PORT` | `8200` | SSE port |
| `MCP_USER_ID` | _(none)_ | Scope MCP reads to one user ID (recommended for SSE) |
| `MCP_ALLOW_REMOTE_SSE` | `false` | Allow binding SSE to non-loopback hosts (also disables DNS rebinding protection) |
| `MCP_ALLOW_UNSCOPED_SSE` | `false` | Allow SSE without `MCP_USER_ID` |

See `docs/environment_variables.md` for full config reference.

## Running

**stdio mode** (default -- for OpenClaw / Claude Desktop):

```bash
python -m app.cli.mcp_server
```

**SSE mode** (HTTP-based integrations):

```bash
python -m app.cli.mcp_server --transport sse --user-id 12345
```

SSE safety defaults:

- Binds to loopback (`127.0.0.1`) unless you explicitly enable remote bind.
- Requires user scoping (`MCP_USER_ID` / `--user-id`) unless you explicitly allow unscoped SSE.
- DNS rebinding protection is enabled by default; when `allow_remote_sse` is set, it is disabled so Docker-internal hostnames (e.g. `bsr-mcp:8200`) are accepted.

## Docker Deployment (SSE)

The `docker-compose.yml` includes a dedicated `mcp` service that runs the server in SSE mode:

```yaml
mcp:
  build: {context: ., dockerfile: Dockerfile}
  container_name: bsr-mcp
  command: ["python", "-m", "app.cli.mcp_server"]
  environment:
    - MCP_TRANSPORT=sse
    - MCP_HOST=0.0.0.0
    - MCP_PORT=8200
    - MCP_USER_ID=${MCP_USER_ID:-94225168}
    - MCP_ALLOW_REMOTE_SSE=true
  volumes:
    - ./data:/data:ro          # read-only DB access
  ports:
    - "127.0.0.1:8200:8200"   # loopback only from host
  networks: [default, karakeep]
```

Key design decisions:

- **Read-only data mount** (`./data:/data:ro`) -- the MCP server only reads the SQLite database.
- **`MCP_ALLOW_REMOTE_SSE=true`** -- required because `0.0.0.0` is non-loopback inside Docker. This also disables the MCP SDK's DNS rebinding protection so that Docker-internal hostnames (`bsr-mcp`, `bsr-mcp:8200`) are accepted in the `Host` header.
- **Loopback port binding** (`127.0.0.1:8200`) -- prevents direct external access from the host network.
- **`karakeep` network** -- shared Docker network allowing other services (e.g. OpenClaw) to reach the MCP server via `http://bsr-mcp:8200/sse`.

### Connecting from another Docker Compose project

To connect from a service in a different compose project (e.g. OpenClaw), ensure both containers share a Docker network and point the MCP client at `http://bsr-mcp:8200/sse`.

Example mcporter config:

```json
{
  "mcpServers": {
    "bite-size-reader": {
      "description": "Personal knowledge base - article summaries, semantic search, collections",
      "baseUrl": "http://bsr-mcp:8200/sse"
    }
  }
}
```

## Tools (17)

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
| `hybrid_search(query, limit, language, min_similarity, rerank)` | Combined keyword + semantic retrieval into a single ranked list |
| `find_similar_articles(summary_id, limit, min_similarity, rerank)` | Find articles semantically similar to an existing summary |
| `chroma_health()` | Check ChromaDB availability and fallback readiness |
| `chroma_index_stats(scan_limit)` | Index coverage stats between SQLite summaries and ChromaDB |
| `chroma_sync_gap(max_scan, sample_size)` | Report sync gaps between SQLite summaries and ChromaDB index |

## Resources (13)

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
| `bsr://chroma/health` | ChromaDB health and fallback status |
| `bsr://chroma/index-stats` | ChromaDB index coverage statistics |
| `bsr://chroma/sync-gap` | Sync gap report between SQLite and ChromaDB |

## Graceful Degradation

- ChromaDB is optional. When unavailable, `semantic_search` and `hybrid_search` fall back to keyword-based `search_articles`. The `chroma_*` tools report availability status rather than failing.
- The MCP server logs to stderr (required by stdio transport) and never writes to stdout outside of MCP protocol messages.

## Implementation

Source: `app/mcp/server.py`

The server uses [FastMCP](https://github.com/modelcontextprotocol/python-sdk) and connects to the same SQLite database as the main bot. Database is initialized once at startup via Peewee ORM.
