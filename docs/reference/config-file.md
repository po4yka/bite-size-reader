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

mcp:
  enabled: false
  transport: stdio
```

## Notes

- OpenRouter is the primary supported provider path for first-run setup.
- Cloud Ollama uses an OpenAI-compatible `/v1` endpoint. Structured output
  quality varies by hosted model, so `ollama.enable_structured_outputs` defaults
  to `false`.
- Firecrawl Cloud is optional. The scraper chain can run with Scrapling,
  Defuddle, Playwright, Crawlee, and direct HTML providers; Phase 2 adds an
  in-compose self-hosted Firecrawl profile.
- Twitter/X extraction is optional and should stay disabled unless explicitly
  needed. X/Twitter ingestion remains out of signal-scoring v0.
