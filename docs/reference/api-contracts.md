# External API Contracts

Reference for external service APIs used by Bite-Size Reader.

**Audience:** Developers, Integrators
**Type:** Reference
**Related:** [SPEC.md § External Systems](../SPEC.md#external-systems--authoritative-docs), [TROUBLESHOOTING](../TROUBLESHOOTING.md)

---

## Overview

Bite-Size Reader integrates with four primary external services:

1. **Firecrawl** - Content extraction
2. **OpenRouter** - LLM completions
3. **Pyrogram** - Telegram MTProto
4. **yt-dlp** - YouTube video downloads

---

## Firecrawl API

**Base URL:** `https://api.firecrawl.dev`
**Authentication:** Bearer token via `Authorization` header
**Documentation:** https://docs.firecrawl.dev/

### POST /v2/scrape

**Purpose:** Extract clean content from web pages.

**Request:**

```http
POST https://api.firecrawl.dev/v2/scrape
Authorization: Bearer fc-xxx...
Content-Type: application/json

{
  "url": "https://example.com/article",
  "formats": ["markdown", "html"],
  "includeTags": ["article", "main"],
  "excludeTags": ["nav", "footer"],
  "onlyMainContent": true,
  "timeout": 90000,
  "mobile": false
}
```

**Request Fields:**

- `url` (string, required) - URL to scrape
- `formats` (array, optional) - Output formats (`["markdown", "html", "links", "screenshot"]`)
- `includeTags` (array, optional) - HTML tags to include
- `excludeTags` (array, optional) - HTML tags to exclude
- `onlyMainContent` (bool, optional) - Extract only main content area
- `timeout` (int, optional) - Timeout in milliseconds (default: 30000)
- `mobile` (bool, optional) - Use mobile user-agent
- `actions` (array, optional) - Browser actions before scraping
- `waitFor` (int, optional) - Wait time before scraping (ms)

**Response (Success):**

```json
{
  "success": true,
  "data": {
    "markdown": "# Article Title\n\nClean markdown content...",
    "html": "<html>...</html>",
    "metadata": {
      "title": "Article Title",
      "description": "Article description",
      "language": "en",
      "sourceURL": "https://example.com/article",
      "ogImage": "https://example.com/image.jpg",
      "keywords": "keyword1, keyword2"
    },
    "links": ["https://example.com/link1", "https://example.com/link2"],
    "llmExtraction": null
  }
}
```

**Response (Error):**

```json
{
  "success": false,
  "error": "Rate limit exceeded",
  "details": {
    "code": "rate_limit_exceeded",
    "retryAfter": 60
  }
}
```

**Status Codes:**

- `200` - Success
- `400` - Invalid request (bad URL, invalid options)
- `401` - Invalid API key
- `402` - Payment required (quota exceeded)
- `429` - Rate limit exceeded
- `500` - Internal server error
- `503` - Service unavailable

**Rate Limits:**

- Free tier: 500 requests/month
- Starter: 10,000 requests/month
- Custom: Varies

**Headers:**

```
X-RateLimit-Limit: 10000
X-RateLimit-Remaining: 9500
X-RateLimit-Reset: 1707490800
```

**Error Handling:**

```python
# app/adapters/content/content_extractor.py
try:
    response = await http_client.post("/v2/scrape", json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()

    if not data.get("success"):
        raise FirecrawlError(data.get("error"), data.get("details"))

    return data["data"]

except httpx.HTTPStatusError as e:
    if e.response.status_code == 429:
        retry_after = int(e.response.headers.get("Retry-After", 60))
        await asyncio.sleep(retry_after)
        # Retry logic...
    raise
```

**Fallback Strategy:**

- Firecrawl fails → Trafilatura (local HTML parser)
- Trafilatura fails → Spacy NLP extraction
- All fail → Error to user

---

## OpenRouter API

**Base URL:** `https://openrouter.ai/api/v1`
**Authentication:** Bearer token via `Authorization` header
**Documentation:** https://openrouter.ai/docs

### POST /chat/completions

**Purpose:** LLM chat completions (OpenAI-compatible).

**Request:**

```http
POST https://openrouter.ai/api/v1/chat/completions
Authorization: Bearer sk-or-xxx...
HTTP-Referer: https://github.com/po4yka/bite-size-reader
X-Title: Bite-Size Reader
Content-Type: application/json

{
  "model": "deepseek/deepseek-v3.2",
  "messages": [
    {
      "role": "system",
      "content": "You are an expert summarization assistant..."
    },
    {
      "role": "user",
      "content": "Summarize this article:\n\n[content]"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 4000,
  "top_p": 1.0,
  "stream": false
}
```

**Request Fields:**

- `model` (string, required) - Model ID (e.g., `deepseek/deepseek-v3.2`)
- `messages` (array, required) - Chat messages with `role` and `content`
- `temperature` (float, optional) - Randomness (0.0-2.0, default: 1.0)
- `max_tokens` (int, optional) - Max completion tokens
- `top_p` (float, optional) - Nucleus sampling (0.0-1.0)
- `stream` (bool, optional) - Stream response (default: false)
- `stop` (array, optional) - Stop sequences
- `frequency_penalty` (float, optional) - Repetition penalty (-2.0 to 2.0)
- `presence_penalty` (float, optional) - Topic diversity (-2.0 to 2.0)

**Response (Success):**

```json
{
  "id": "chatcmpl-xxx",
  "model": "deepseek/deepseek-v3.2",
  "created": 1707490800,
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"summary_250\": \"...\", \"summary_1000\": \"...\", ...}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 800,
    "total_tokens": 2300
  }
}
```

**Response (Error):**

```json
{
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error",
    "code": "rate_limit_exceeded"
  }
}
```

**Status Codes:**

- `200` - Success
- `400` - Invalid request (bad model, invalid messages)
- `401` - Invalid API key
- `402` - Insufficient credits
- `429` - Rate limit exceeded
- `500` - Internal server error
- `503` - Model temporarily unavailable

**Rate Limits:**

- Varies by model (check OpenRouter dashboard)
- Free models: 10-20 requests/minute
- Paid models: 100+ requests/minute

**Model Fallback Chain:**

```python
# app/config/settings.py
OPENROUTER_MODEL = "deepseek/deepseek-v3.2"
OPENROUTER_FALLBACK_MODELS = [
    "moonshotai/kimi-k2.5",
    "qwen/qwen3-max",
    "deepseek/deepseek-r1",
    "google/gemini-2.0-flash-001:free"
]
```

**Error Handling:**

```python
# app/adapters/openrouter/openrouter_client.py
async def complete_with_fallback(messages, model=None):
    models = [model] + FALLBACK_MODELS if model else [PRIMARY_MODEL] + FALLBACK_MODELS

    for model_name in models:
        try:
            return await complete(messages, model=model_name)
        except OpenRouterError as e:
            if e.status_code == 503:  # Model unavailable
                logger.warning(f"Model {model_name} unavailable, trying fallback")
                continue
            raise

    raise OpenRouterError("All models failed")
```

**Cost Tracking:**

```python
# app/db/models.py (llm_calls table)
cost_usd = (prompt_tokens * pricing["prompt"] + completion_tokens * pricing["completion"]) / 1_000_000

# Example pricing (per 1M tokens):
# deepseek/deepseek-v3.2: $0.14 prompt, $0.28 completion
# qwen/qwen3-max: $0.20 prompt, $0.60 completion
```

---

## Pyrogram (Telegram)

**Library:** PyroTGFork (fork of Pyrogram)
**Protocol:** Telegram MTProto
**Documentation:** https://telegramplayground.github.io/pyrogram/

### Authentication

**Bot Token Authentication:**

```python
# app/adapters/telegram/telegram_bot.py
from pyrogram import Client

app = Client(
    "bite_size_reader",
    api_id=API_ID,  # From my.telegram.org
    api_hash=API_HASH,  # From my.telegram.org
    bot_token=BOT_TOKEN  # From @BotFather
)

await app.start()
```

**Environment Variables:**

```bash
API_ID=12345678  # Telegram API ID
API_HASH=abc123...  # Telegram API hash
BOT_TOKEN=123456:ABC-DEF...  # Bot token from @BotFather
```

### Receiving Messages

**Message Handler:**

```python
@app.on_message(filters.private & filters.text)
async def handle_text_message(client: Client, message: Message):
    # Access message fields
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    message_id = message.id
    date = message.date

    # Check for forwarded message
    if message.forward_from_chat:
        forward_from_chat_id = message.forward_from_chat.id
        forward_from_message_id = message.forward_from_message_id
        forward_date = message.forward_date
```

**Message Fields:**

- `message.id` (int) - Unique message ID
- `message.from_user` (User) - Sender
- `message.chat` (Chat) - Chat where message was sent
- `message.text` (str) - Message text
- `message.date` (datetime) - Message timestamp
- `message.forward_from_chat` (Chat, nullable) - Forwarded from chat
- `message.forward_from_message_id` (int, nullable) - Forwarded message ID
- `message.forward_date` (datetime, nullable) - Original message timestamp
- `message.entities` (list[MessageEntity]) - Text entities (URLs, mentions, etc.)

### Sending Messages

**Simple Reply:**

```python
await message.reply_text("Response text")
```

**With Formatting:**

```python
await message.reply_text(
    "**Bold** *italic* `code`",
    parse_mode=enums.ParseMode.MARKDOWN
)
```

**Edit Message:**

```python
await message.edit_text("Updated text")
```

**Send Document:**

```python
await client.send_document(
    chat_id=chat_id,
    document="summary.json",
    caption="Summary JSON"
)
```

**Error Handling:**

```python
from pyrogram.errors import FloodWait, MessageNotModified

try:
    await message.reply_text("Response")
except FloodWait as e:
    await asyncio.sleep(e.value)  # Wait before retrying
    await message.reply_text("Response")
except MessageNotModified:
    pass  # Message content unchanged, ignore
```

**Rate Limits:**

- Private messages: 30 messages/second
- Groups: 20 messages/minute
- Flood wait: Dynamic, 5-120 seconds

---

## yt-dlp (YouTube)

**Library:** yt-dlp (Python)
**Documentation:** https://github.com/yt-dlp/yt-dlp

### Video Download

**Command-Line:**

```bash
yt-dlp \
  -f "bestvideo[height<=1080]+bestaudio/best[height<=1080]" \
  -o "/data/videos/%(id)s.%(ext)s" \
  --write-info-json \
  --write-thumbnail \
  --write-subs \
  --sub-langs "en,ru" \
  --embed-subs \
  --merge-output-format mp4 \
  https://youtube.com/watch?v=VIDEO_ID
```

**Python API:**

```python
# app/adapters/youtube/video_downloader.py
import yt_dlp

ydl_opts = {
    'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
    'outtmpl': '/data/videos/%(id)s.%(ext)s',
    'writeinfojson': True,
    'writethumbnail': True,
    'writesubtitles': True,
    'subtitleslangs': ['en', 'ru'],
    'merge_output_format': 'mp4',
    'quiet': False,
    'no_warnings': False,
    'progress_hooks': [progress_hook],
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=True)

    # Access metadata
    video_id = info['id']
    title = info['title']
    duration = info['duration']
    uploader = info['uploader']
    upload_date = info['upload_date']  # YYYYMMDD
    view_count = info['view_count']
```

**Output Files:**

- `VIDEO_ID.mp4` - Merged video+audio
- `VIDEO_ID.info.json` - Metadata JSON
- `VIDEO_ID.webp` - Thumbnail
- `VIDEO_ID.en.vtt` - Subtitles (if available)

**Error Handling:**

```python
from yt_dlp.utils import DownloadError, ExtractorError

try:
    info = ydl.extract_info(url, download=True)
except DownloadError as e:
    if "unavailable" in str(e).lower():
        # Video removed, private, or geo-blocked
        raise VideoUnavailableError(str(e))
    raise
except ExtractorError as e:
    # Invalid URL or unsupported site
    raise InvalidVideoURLError(str(e))
```

**Prerequisites:**

- **ffmpeg** installed (for merging video+audio streams)

  ```bash
  apt-get install ffmpeg  # Debian/Ubuntu
  brew install ffmpeg  # macOS
  ```

### Transcript Extraction

**Library:** youtube-transcript-api

**Python API:**

```python
# app/adapters/youtube/transcript_extractor.py
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

try:
    # Fetch transcript (auto-generated or manual)
    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'ru'])

    # transcript is list of dicts:
    # [{'text': 'Hello', 'start': 0.0, 'duration': 2.5}, ...]

    # Join into full text
    full_transcript = ' '.join([entry['text'] for entry in transcript])

except NoTranscriptFound:
    # No transcript available
    raise TranscriptUnavailableError(f"No transcript for {video_id}")

except TranscriptsDisabled:
    # Transcripts disabled by uploader
    raise TranscriptUnavailableError(f"Transcripts disabled for {video_id}")
```

**Fallback Strategy:**

- Try youtube-transcript-api first (faster)
- If unavailable, check yt-dlp subtitles
- If both fail, error to user

---

## Service Comparison

| Service | Purpose | Free Tier | Rate Limits | Fallback |
|---------|---------|-----------|-------------|----------|
| Firecrawl | Content extraction | 500 req/month | 10 req/min | Trafilatura |
| OpenRouter | LLM completions | Yes (free models) | Varies by model | Model fallback chain |
| Pyrogram | Telegram client | Unlimited | 30 msg/sec | Built-in FloodWait handling |
| yt-dlp | YouTube download | Unlimited | YouTube rate limits | youtube-transcript-api |

---

## Environment Configuration

**Required Variables:**

```bash
# Firecrawl
FIRECRAWL_API_KEY=fc-xxx...
FIRECRAWL_TIMEOUT_SEC=90

# OpenRouter
OPENROUTER_API_KEY=sk-or-xxx...
OPENROUTER_MODEL=deepseek/deepseek-v3.2
OPENROUTER_FALLBACK_MODELS=moonshotai/kimi-k2.5,qwen/qwen3-max

# Telegram
API_ID=12345678
API_HASH=abc123...
BOT_TOKEN=123456:ABC-DEF...

# YouTube (optional)
YOUTUBE_DOWNLOAD_ENABLED=true
YOUTUBE_DOWNLOAD_VIDEO=true
YOUTUBE_DOWNLOAD_TRANSCRIPT=true
```

---

## See Also

- [SPEC.md § External Systems](../SPEC.md#external-systems--authoritative-docs) - Canonical documentation links
- [TROUBLESHOOTING § External API Errors](../TROUBLESHOOTING.md#external-api-errors) - Common issues
- [API Error Codes](api-error-codes.md) - Complete error reference

---

**Last Updated:** 2026-02-09
