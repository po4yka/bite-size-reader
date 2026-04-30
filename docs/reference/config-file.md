# Optional YAML Configuration

`ratatoskr.yaml` is the Phase 1 home for power-user settings. Keep first-run
secrets in `.env`; use YAML for scraper tuning, provider model choices, YouTube,
Twitter/X, MCP, monitoring-adjacent settings, and other optional behavior.

## Search Order

Ratatoskr loads the first file found:

1. `RATATOSKR_CONFIG`, when set
2. `./ratatoskr.yaml`
3. `./config/ratatoskr.yaml`
4. `/app/config/ratatoskr.yaml`

Merge precedence is:

`code defaults < config/models.yaml < ratatoskr.yaml < .env < process env`

Environment variables remain the final override for container platforms and
secret managers. Deprecated env vars fail startup with an actionable message.

## Minimal `.env`

Only these values are required for the Telegram bot + OpenRouter path:

```env
API_ID=123456
API_HASH=replace_with_telegram_api_hash
BOT_TOKEN=1234567890:replace_with_botfather_token_secret
ALLOWED_USER_IDS=123456789
OPENROUTER_API_KEY=sk-or-replace_with_openrouter_key
```

`JWT_SECRET_KEY` is required only when web/API/browser-extension JWT auth is
enabled. Generate it with `openssl rand -hex 32`.

## Example `ratatoskr.yaml`

```yaml
runtime:
  log_level: INFO
  request_timeout_sec: 60
  preferred_lang: auto
  max_concurrent_calls: 4

openrouter:
  model: deepseek/deepseek-v3.2
  fallback_models:
    - qwen/qwen3.5-plus-02-15
    - moonshotai/kimi-k2-0905
  flash_model: qwen/qwen3.5-flash-02-23

ollama:
  base_url: https://ollama.example.com/v1
  api_key: replace_with_cloud_ollama_token
  model: llama3.3
  enable_structured_outputs: false

scraper:
  profile: balanced
  provider_order:
    - scrapling
    - defuddle
    - firecrawl
    - playwright
    - crawlee
    - direct_html
  firecrawl_self_hosted_enabled: false

firecrawl:
  api_key: ""
  timeout_sec: 90
  wait_for_ms: 3000

youtube:
  enabled: true
  storage_path: /data/videos
  preferred_quality: 1080p
  subtitle_languages:
    - en
    - ru

twitter:
  enabled: false
  prefer_firecrawl: true
  playwright_enabled: false

signal_ingestion:
  enabled: true
  max_items_per_source: 30
  hn_enabled: true
  hn_feeds:
    - top
    - best
  reddit_enabled: true
  reddit_subreddits:
    - selfhosted
    - python
  reddit_listing: hot
  reddit_requests_per_minute: 60
  twitter_enabled: false
  twitter_ack_cost: false

mcp:
  enabled: false
  transport: stdio
```

## Notes

- OpenRouter is the primary supported provider path for first-run setup.
- Cloud Ollama uses an OpenAI-compatible `/v1` endpoint. Structured output
  quality varies by hosted model, so `ollama.enable_structured_outputs` defaults
  to `false`. When using `LLM_PROVIDER=ollama`, failures usually fall into four
  buckets: `/models` is unreachable, the model name is not installed by the
  remote provider, the provider times out on long articles, or the model returns
  weak/invalid JSON. Prefer models that advertise OpenAI-compatible chat
  completions and test summaries before using them unattended.
- Firecrawl Cloud is optional. The scraper chain can run with Scrapling,
  Defuddle, Playwright, Crawlee, and direct HTML providers; Phase 2 adds an
  in-compose self-hosted Firecrawl profile.
- Signal ingestion optional sources are disabled unless `signal_ingestion.enabled`
  and the per-source flag are both true. Hacker News uses the official Firebase
  API and has no credentials. Reddit uses public subreddit JSON with a default
  60 requests/minute guard, below the free-tier 100 requests/minute ceiling.
  Substack is handled as RSS via `/feed`; use existing RSS subscription flows.
- Twitter/X extraction is optional and should stay disabled unless explicitly
  needed. X/Twitter proactive ingestion is also disabled by default and requires
  explicit `twitter_ack_cost: true` / `TWITTER_INGESTION_ACK_COST=true`; the
  Basic tier is approximately $200/month and the project uses a bring-your-own
  token model for any future polling adapter.
