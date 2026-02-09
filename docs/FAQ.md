# Frequently Asked Questions (FAQ)

Common questions about Bite-Size Reader.

## Table of Contents

- [General](#general)
- [Installation](#installation)
- [Configuration](#configuration)
- [Features](#features)
- [YouTube Support](#youtube-support)
- [Web Search](#web-search)
- [Performance](#performance)
- [Security](#security)
- [Integration](#integration)
- [Cost Optimization](#cost-optimization)

---

## General

### What is Bite-Size Reader?

Bite-Size Reader is an AI-powered Telegram bot that transforms long web articles and YouTube videos into structured, searchable summaries. It uses:

- **Firecrawl** for clean content extraction
- **OpenRouter** (or OpenAI/Anthropic) for LLM-powered summarization
- **yt-dlp** for YouTube video downloads and transcript extraction

**Key Features**:

- Strict JSON summary contract (35+ fields)
- Multi-language support (English, Russian)
- Semantic search (ChromaDB, vector embeddings)
- Mobile API (JWT auth, multi-device sync)
- YouTube video + transcript support
- Optional web search enrichment
- Self-hosted, privacy-focused

### Who is it for?

- **Information Workers**: Researchers, analysts, students who read many articles daily
- **Content Curators**: People who save and organize knowledge
- **Privacy-Conscious Users**: Self-hosting ensures your reading history stays private
- **Developers**: Extensible architecture (hexagonal, multi-agent), MCP server for AI agents

### Is it free?

The software is **free and open-source** (BSD 3-Clause license), but you'll need API keys:

- **Firecrawl**: 500 free credits/month (~500 articles), then $25/month for 5,000 credits
- **OpenRouter**: Pay-per-use ($0.01-0.05 per summary depending on model)
  - Alternative: Use free models (Google Gemini 2.0, some DeepSeek R1 providers offer free tier)
- **YouTube**: Free (uses yt-dlp, no API costs)

**Estimated Monthly Cost**: $10-30 for moderate use (50-100 summaries/month).

See [Cost Optimization](#cost-optimization) for ways to minimize costs.

### How does it work?

1. **You send a URL** (article or YouTube video) to the Telegram bot
2. **Content extraction**: Firecrawl scrapes the article (or yt-dlp downloads YouTube transcript)
3. **LLM summarization**: OpenRouter sends content to an LLM (e.g., DeepSeek, Qwen, Kimi)
4. **Structured output**: LLM returns JSON summary (validated, self-corrected via multi-agent pipeline)
5. **Storage**: Summary stored in SQLite with metadata (topics, entities, timestamps)
6. **Reply**: Bot sends formatted summary back to Telegram

### What makes it different from ChatGPT?

- **Structured Output**: 35+ JSON fields (TLDR, key ideas, topic tags, entities, readability scores) vs free-form text
- **Persistent Storage**: All summaries saved and searchable (semantic + full-text search)
- **Multi-Interface**: Telegram, mobile app, CLI, MCP server access the same data
- **Self-Hosted**: Your data never leaves your server
- **YouTube Support**: Extract and summarize video transcripts
- **Optimized for Reading**: Designed specifically for article summarization, not general chat

---

## Installation

### What are the system requirements?

**Minimum**:

- Python 3.13+
- 512 MB RAM (1 GB recommended with ChromaDB)
- 5 GB disk space (more if storing YouTube videos)
- Linux, macOS, or Windows (WSL recommended on Windows)

**Optional (for YouTube)**:

- ffmpeg (video/audio merging)

**Optional (for semantic search)**:

- ChromaDB server (or use embedded mode)

### Can I run it on a Raspberry Pi?

Yes, but with caveats:

- **Pi 4 (4GB+)**: Works well, but disable ChromaDB or use CPU-only mode
- **Pi 3 or older**: Too slow, ChromaDB embeddings will struggle
- **Docker**: Recommended for easy deployment on Pi

```bash
# Pi-optimized config
CHROMA_DEVICE=cpu
ENABLE_CHROMA=false  # Or use lightweight embedding model
YOUTUBE_VIDEO_QUALITY=720  # Lower quality for smaller downloads
```

### Does it support ARM (M1/M2 Macs, Raspberry Pi)?

Yes. Some dependencies (chromadb, sentence-transformers) may need compilation:

```bash
# macOS M1/M2
brew install cmake pkg-config
pip install -r requirements.txt

# Raspberry Pi (Debian/Raspbian)
sudo apt-get install build-essential python3-dev
pip install -r requirements.txt
```

### Can I run it without Docker?

Yes. Use Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

See [tutorials/local-development.md](tutorials/local-development.md) for full guide.

---

## Configuration

### Which environment variables are required?

**Absolutely required**:

```bash
API_ID=...              # Telegram API ID (from https://my.telegram.org/apps)
API_HASH=...            # Telegram API hash
BOT_TOKEN=...           # Bot token (from @BotFather)
ALLOWED_USER_IDS=...    # Your Telegram user ID
FIRECRAWL_API_KEY=...   # Firecrawl API key
OPENROUTER_API_KEY=...  # OpenRouter API key
```

**Optional but recommended**:

```bash
OPENROUTER_MODEL=deepseek/deepseek-v3.2
OPENROUTER_FALLBACK_MODELS=qwen/qwen3-max,moonshotai/kimi-k2.5
DB_PATH=/data/app.db
LOG_LEVEL=INFO
```

See [environment_variables.md](environment_variables.md) for full reference (250+ variables).

### How do I find my Telegram user ID?

1. Message `@userinfobot` on Telegram
2. Copy the numeric ID
3. Add to `ALLOWED_USER_IDS` environment variable
4. Restart bot

### Can I use OpenAI instead of OpenRouter?

Yes. Set `LLM_PROVIDER=openai`:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
OPENAI_FALLBACK_MODELS=gpt-4o-mini
```

Or Anthropic:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

### How do I enable multi-user access?

Add multiple user IDs to `ALLOWED_USER_IDS`:

```bash
ALLOWED_USER_IDS=123456789,987654321,555666777
```

All users share the same database (no per-user isolation). This is designed for personal use or small teams, not multi-tenant SaaS.

---

## Features

### What types of content can it summarize?

**Supported**:

- ✅ Web articles (news sites, blogs, documentation)
- ✅ YouTube videos (any format: watch, shorts, live, music)
- ✅ Forwarded Telegram channel posts
- ✅ PDFs (with embedded image analysis)
- ✅ Long-form content (up to 256k tokens with long-context models)

**Not Supported**:

- ❌ Paywalled content (WSJ, NYT, Medium members-only)
- ❌ Sites with CAPTCHA challenges (most get bypassed by Firecrawl proxies)
- ❌ Videos without transcripts (unless Whisper transcription enabled)

### Does it support languages other than English?

Yes. Supports **English and Russian** out of the box:

- Language detection (`PREFERRED_LANG=auto` by default)
- Separate prompts for English (`app/prompts/en/`) and Russian (`app/prompts/ru/`)
- Russian content gets Russian summary and vice versa

**Adding new languages**: Copy `app/prompts/en/summary_system.txt` to new language directory, translate prompt, update `app/core/lang.py`.

### Can I search my summaries?

Yes. Three search modes:

1. **Full-Text Search** (FTS5): Fast keyword search

   ```sql
   SELECT * FROM topic_search_index WHERE topic_search_index MATCH 'python tutorial';
   ```

2. **Semantic Search** (ChromaDB): Natural language queries

   ```bash
   # Via CLI
   python -m app.cli.search --query "machine learning basics"

   # Via Telegram
   /search machine learning
   ```

3. **Hybrid Search**: Combines full-text + semantic + reranking

See [SPEC.md § Search](SPEC.md#search) for details.

### What is the summary JSON contract?

Every summary follows a strict schema with 35+ fields:

- **Core**: `summary_250` (≤250 chars), `summary_1000`, `tldr`, `key_ideas`
- **Metadata**: `title`, `url`, `word_count`, `estimated_reading_time_min`
- **Semantic**: `topic_tags`, `entities`, `semantic_chunks`, `seo_keywords`
- **Quality**: `confidence`, `readability`, `hallucination_risk`

See [reference/summary-contract.md](reference/summary-contract.md) for full specification.

### Can I export summaries?

Yes. Multiple export formats:

- **JSON**: Via mobile API (`GET /v1/summaries`)
- **PDF**: Via `weasyprint` (roadmap: not yet implemented)
- **Markdown**: Via CLI export (roadmap: not yet implemented)
- **SQLite**: Direct database access (`data/app.db`)

### Does it deduplicate URLs?

Yes. All URLs normalized and hashed (`sha256`) before processing:

- `https://example.com/article?utm_source=twitter` → deduplicated
- `http://example.com/article` → deduplicated (HTTPS normalized)
- Same article reposted won't be processed twice (returns cached summary)

---

## YouTube Support

### What YouTube platforms are supported?

All major formats:

- ✅ Standard videos (`youtube.com/watch?v=...`)
- ✅ Shorts (`youtube.com/shorts/...`)
- ✅ Live streams (`youtube.com/live/...`)
- ✅ Embedded videos (`youtube.com/embed/...`)
- ✅ Mobile links (`m.youtube.com/...`, `youtu.be/...`)
- ✅ YouTube Music (`music.youtube.com/...`)

### How does transcript extraction work?

1. **Try youtube-transcript-api** (fast, no download)
   - Fetches auto-generated or manual captions
   - Works for 90%+ of videos

2. **Fallback to yt-dlp** (slower, downloads video)
   - Downloads video + extracts audio
   - Sends audio to Whisper API for transcription (if `WHISPER_API_KEY` set)

### What if a video has no transcript?

**Default behavior**: Fails with error message.

**Workaround**: Enable Whisper transcription (requires API key or local Whisper model):

```bash
ENABLE_WHISPER_TRANSCRIPTION=true
WHISPER_API_KEY=...  # Or leave empty for local Whisper
```

### How much storage do YouTube downloads use?

Depends on video quality and length:

- **1080p, 10-minute video**: ~200 MB
- **720p, 10-minute video**: ~100 MB
- **Audio-only** (if video not needed): ~10 MB

**Storage management**:

```bash
YOUTUBE_AUTO_CLEANUP_DAYS=7      # Delete after 7 days
YOUTUBE_MAX_STORAGE_GB=10        # Max 10 GB total
```

### Can I disable video download (audio only)?

Not yet, but planned. Current workaround: Set low quality

```bash
YOUTUBE_VIDEO_QUALITY=480  # Smaller files
```

Or disable YouTube entirely:

```bash
ENABLE_YOUTUBE=false
```

---

## Web Search

### What is web search enrichment?

Optional feature that queries the web for current context before summarizing:

1. **Extract keywords** from article (e.g., "climate change 2025")
2. **Search DuckDuckGo** (or Google if API key provided)
3. **Add top 3 results to LLM prompt** as additional context
4. **LLM generates summary** with up-to-date information

**Benefits**: Corrects outdated info, adds recent developments, fact-checks claims.

### When should I enable it?

**Enable for**:

- News articles (time-sensitive topics)
- Research papers (need latest findings)
- Tutorial articles (check if still relevant)

**Disable for**:

- Timeless content (classic literature, historical docs)
- Privacy-sensitive content (internal docs, private blogs)
- Cost sensitivity (adds ~500 tokens per summary)

```bash
# Enable
WEB_SEARCH_ENABLED=true
WEB_SEARCH_PROVIDER=duckduckgo  # Or google (requires API key)
```

### Does it cost extra?

Yes, but minimal:

- **Web search API**: DuckDuckGo is free, Google costs ~$0.005 per query
- **LLM tokens**: Adds ~500 tokens (~$0.005-0.01 depending on model)

**Total extra cost**: ~$0.01 per summary.

---

## Performance

### How long does a summary take?

**Typical**:

- **Articles**: 5-10 seconds (2-3s Firecrawl + 3-5s LLM)
- **YouTube videos**: 10-20 seconds (transcript extraction + LLM)
- **Long articles (20k+ words)**: 15-30 seconds (chunking + longer LLM processing)

**Factors**:

- Model speed (DeepSeek fast, GPT-4 slower)
- Network latency
- Article length
- Web search enabled/disabled

### Can I make it faster?

Yes. Several optimizations:

1. **Use faster model**:

   ```bash
   OPENROUTER_MODEL=qwen/qwen3-max  # Faster than DeepSeek
   ```

2. **Increase concurrency**:

   ```bash
   MAX_CONCURRENT_CALLS=5  # Default: 3
   ```

3. **Disable optional features**:

   ```bash
   WEB_SEARCH_ENABLED=false
   SUMMARY_TWO_PASS_ENABLED=false
   ```

4. **Reduce content length**:

   ```bash
   MAX_CONTENT_LENGTH_TOKENS=30000  # Default: 50000
   ```

### Why is memory usage high?

**Common causes**:

1. **ChromaDB embeddings** (sentence-transformers model): 500 MB - 1 GB
2. **YouTube downloads** in memory before writing to disk
3. **LLM response buffering**

**Solutions**:

```bash
# Use smaller embedding model
CHROMA_EMBEDDING_MODEL=all-MiniLM-L6-v2  # ~100 MB

# Disable ChromaDB if not using search
ENABLE_CHROMA=false

# Limit ChromaDB memory
CHROMA_MAX_MEMORY_MB=512
```

### Can I batch-process multiple URLs?

Yes, via CLI:

```bash
# From file (one URL per line)
python -m app.cli.summary --accept-multiple --url-file urls.txt

# Output to JSON
python -m app.cli.summary --accept-multiple --url-file urls.txt --json-path summaries.json
```

**Note**: Respects rate limits and concurrency settings.

---

## Security

### Is my data private?

Yes, if self-hosted:

- **No data leaves your server** (except API calls to Firecrawl/OpenRouter)
- **API calls redacted**: Authorization headers never logged
- **SQLite database**: Stored locally (`data/app.db`)
- **No telemetry**: No usage analytics sent anywhere

**Privacy considerations**:

- Firecrawl sees your URLs (use trafilatura fallback for sensitive sites)
- OpenRouter/OpenAI see article content (use on-premise LLM if needed)
- Telegram sees your bot interactions (use Telegram's privacy settings)

### Can multiple users access it safely?

**Single-User Mode** (default):

- One database, no user isolation
- All users see all summaries
- Suitable for personal use or small trusted teams (family, close colleagues)

**Multi-User Mode** (not implemented):

- Would require user-specific databases or row-level security
- See [ADR-0003](adr/0003-single-user-access-control.md) for decision rationale

### How are API keys stored?

**Environment variables only** (`.env` file):

```bash
# .env file (not committed to git)
FIRECRAWL_API_KEY=fc-...
OPENROUTER_API_KEY=sk-or-...
BOT_TOKEN=1234567890:ABCDEF...
```

**Never stored in**:

- Database
- Logs (Authorization headers redacted)
- Git repository (`.env` in `.gitignore`)

### What if someone gets my bot token?

**Impact**: Attacker can send messages as your bot, but can't:

- See your summaries (database access required)
- Trigger summarization (ALLOWED_USER_IDS whitelist blocks them)
- Access Mobile API (separate JWT authentication)

**Response**:

1. Revoke token via @BotFather on Telegram
2. Generate new token
3. Update `BOT_TOKEN` in `.env`
4. Restart bot

---

## Integration

### Does it have a mobile app?

Yes. **Mobile API** (FastAPI) provides:

- JWT authentication (Telegram login exchange)
- Summary fetching (`GET /v1/summaries`)
- Multi-device sync (full + delta modes)
- Collection management
- Offline-first support

See [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) for API reference.

**Note**: Mobile app UI not included (API only). Build your own client or use Telegram bot.

### Can I integrate with other apps?

Yes. Multiple integration options:

1. **REST API** (FastAPI): Build custom clients
2. **MCP Server**: Expose to Claude Desktop (or any MCP client)
3. **SQLite Database**: Direct database access for custom scripts
4. **CLI Tools**: Batch processing, search, export

See [mcp_server.md](mcp_server.md) for MCP integration.

### Does it integrate with Notion/Obsidian/Roam?

Not directly, but you can:

1. **Export to Markdown** (CLI tool, roadmap)
2. **Sync via Mobile API** (build custom sync script)
3. **Direct Database Access** (query SQLite, convert to Markdown)

**Karakeep Integration**: Built-in sync with Karakeep (self-hosted bookmark manager).

```bash
# Enable Karakeep sync
KARAKEEP_SYNC_ENABLED=true
KARAKEEP_BASE_URL=https://karakeep.example.com
KARAKEEP_API_KEY=...

# Sync command
/sync_karakeep
```

### Can I use it as a Slack bot?

Not out-of-box, but adaptable:

1. **Replace Telegram adapter** (`app/adapters/telegram/`) with Slack adapter
2. **Use hexagonal architecture** (core logic unchanged)
3. **Implement Slack OAuth** (instead of Telegram access control)

See [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](HEXAGONAL_ARCHITECTURE_QUICKSTART.md) for architecture guide.

---

## Cost Optimization

### How can I minimize API costs?

**Free tier strategies**:

1. **Use free models** (OpenRouter):

   ```bash
   OPENROUTER_MODEL=google/gemini-2.0-flash-001:free
   OPENROUTER_FALLBACK_MODELS=deepseek/deepseek-r1:free
   ```

2. **Maximize Firecrawl free tier** (500 credits/month):
   - Use trafilatura fallback for simple sites
   - Only send complex sites to Firecrawl

   ```bash
   CONTENT_EXTRACTION_FALLBACK=true  # Try trafilatura first
   ```

3. **Cache aggressively**:

   ```bash
   ENABLE_REDIS=true
   REDIS_CACHE_TTL_SECONDS=86400  # 24 hours
   ```

4. **Disable optional features**:

   ```bash
   WEB_SEARCH_ENABLED=false
   SUMMARY_TWO_PASS_ENABLED=false
   ```

### What are the cheapest models that work well?

**Ranked by cost/quality** (as of Feb 2026):

1. **Free tier**: `google/gemini-2.0-flash-001:free` (best free option)
2. **Ultra-cheap**: `deepseek/deepseek-v3.2` (~$0.01/summary)
3. **Cheap + good**: `qwen/qwen3-max` (~$0.02/summary)
4. **Balanced**: `moonshotai/kimi-k2.5` (~$0.03/summary, great for long content)

**Not recommended** (too expensive for this use case):

- `gpt-4-turbo`: ~$0.20/summary
- `claude-opus-4`: ~$0.30/summary

### Can I run an on-premise LLM?

Yes, but requires setup:

1. **Run local LLM** (Ollama, LM Studio, vLLM):

   ```bash
   ollama run llama3.2:70b
   ```

2. **Point bot to local endpoint**:

   ```bash
   LLM_PROVIDER=openai  # Use OpenAI-compatible API
   OPENAI_API_KEY=dummy  # Not needed for local
   OPENAI_BASE_URL=http://localhost:11434/v1
   OPENAI_MODEL=llama3.2:70b
   ```

3. **Disable Firecrawl** (use trafilatura):

   ```bash
   CONTENT_EXTRACTION_FALLBACK=true
   # Don't call Firecrawl at all (set dummy key)
   ```

**Hardware requirements**: 70B model needs 40+ GB VRAM (A100, H100, or multiple GPUs).

### Is caching worth it?

**Yes, if you re-summarize URLs often**:

- Same URL sent twice → cached summary returned (0 API cost)
- Redis cache hit rate: ~30-40% for news aggregators who share links

**Not worth it if**:

- You never re-read articles
- Redis adds complexity you don't want

**Enable caching**:

```bash
ENABLE_REDIS=true
REDIS_CACHE_TTL_SECONDS=604800  # 7 days
```

---

## Related Documentation

- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Debugging guide
- [environment_variables.md](environment_variables.md) - Configuration reference
- [DEPLOYMENT.md](DEPLOYMENT.md) - Setup and deployment
- [MOBILE_API_SPEC.md](MOBILE_API_SPEC.md) - REST API specification
- [SPEC.md](SPEC.md) - Technical specification
- [README.md](../README.md) - Project overview

---

**Last Updated**: 2026-02-09

**Have a question not answered here?** [Open an issue](https://github.com/po4yka/bite-size-reader/issues) or check [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
