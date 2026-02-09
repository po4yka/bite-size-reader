---
name: telegram-testing
description: Test Telegram bot functionality locally without running the full bot, including CLI summary runner, message simulation, and workflow validation. Use when testing bot features or debugging message handling.
version: 1.0.0
allowed-tools: Bash, Read, Write
---

# Telegram Testing Skill

Test Telegram bot functionality locally using CLI tools and simulations.

## Local CLI Summary Runner

The CLI runner lets you test URL processing without Telegram credentials.

### Basic Usage

```bash
# Summarize a single URL
python -m app.cli.summary --url https://example.com/article

# With custom output
python -m app.cli.summary \
  --url https://example.com/article \
  --json-path summary.json \
  --log-level DEBUG

# Auto-accept multiple URLs
python -m app.cli.summary \
  --url "https://example.com/1 https://example.com/2" \
  --accept-multiple

# Simulate message text (like Telegram input)
python -m app.cli.summary "/summarize https://example.com/article"
```

### Environment Setup

The CLI automatically loads `.env` from current directory or project root:

```bash
# Required for CLI runner
FIRECRAWL_API_KEY=fc-...
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4
DB_PATH=./data/app.db

# Optional
DEBUG_PAYLOADS=1
LOG_LEVEL=DEBUG
PREFERRED_LANG=auto
```

**Note**: Telegram credentials (`API_ID`, `API_HASH`, `BOT_TOKEN`) are NOT required—the CLI generates stub credentials automatically.

### CLI Features

- **Full pipeline**: URL normalization → Firecrawl → OpenRouter → JSON validation
- **Deduplication**: Respects `dedupe_hash` (won't re-crawl same URL)
- **Insights generation**: Optional advanced analysis with retry logic
- **JSON repair**: Handles malformed LLM output
- **Correlation IDs**: Generates unique IDs for tracing

### Testing Specific Workflows

#### Test URL Normalization

```bash
python << 'EOF'
from app.core.url_utils import normalize_url, compute_dedupe_hash

test_urls = [
    "https://Example.com/Article?utm_source=test",
    "https://example.com/article",
    "https://example.com/article/",
]

for url in test_urls:
    normalized = normalize_url(url)
    hash_val = compute_dedupe_hash(normalized)
    print(f"Original: {url}")
    print(f"Normalized: {normalized}")
    print(f"Hash: {hash_val}\n")
EOF
```

#### Test Summary Validation

```bash
python << 'EOF'
from app.core.summary_contract import validate_summary_json

test_summary = {
    "summary_250": "Short summary here.",
    "summary_1000": "Longer summary with more details.",
    "tldr": "TLDR version",
    "key_ideas": ["idea1", "idea2", "idea3", "idea4", "idea5"],
    "topic_tags": ["#tech", "#ai"],
    "entities": {"people": [], "organizations": [], "locations": []},
    "estimated_reading_time_min": 5,
    "key_stats": [],
    "answered_questions": ["What is this?"],
    "readability": {"method": "Flesch-Kincaid", "score": 10.0, "level": "Grade 10"},
    "seo_keywords": ["keyword1", "keyword2"]
}

try:
    validated = validate_summary_json(test_summary)
    print("✓ Valid summary!")
except Exception as e:
    print(f"✗ Validation failed: {e}")
EOF
```

#### Test Language Detection

```bash
python << 'EOF'
from app.core.lang import detect_language

texts = [
    "This is an English text about technology.",
    "Это русский текст о технологиях.",
    "Mixed текст with both languages",
]

for text in texts:
    lang = detect_language(text)
    print(f"Text: {text[:50]}...")
    print(f"Detected: {lang}\n")
EOF
```

## Simulating Telegram Messages

### Message Models

See `app/models/telegram/telegram_message.py` for data structures:

```python
from app.models.telegram.telegram_message import TelegramMessage
from app.models.telegram.telegram_chat import TelegramChat

# Create test message
test_message = TelegramMessage(
    message_id=12345,
    date=1234567890,
    chat=TelegramChat(id=111, type="private"),
    text="https://example.com/article",
    from_user={"id": 123456789, "username": "testuser"}
)
```

### Test Message Router

```python
# Test URL extraction
from app.adapters.telegram.message_router import MessageRouter

# Check if message contains URL
# See app/adapters/telegram/message_router.py for routing logic
```

### Test Access Control

```bash
python << 'EOF'
import os
os.environ['ALLOWED_USER_IDS'] = '123456789,987654321'

from app.adapters.telegram.access_controller import AccessController

controller = AccessController()

# Test allowed user
print(f"User 123456789 allowed: {controller.is_allowed(123456789)}")

# Test blocked user
print(f"User 999999999 allowed: {controller.is_allowed(999999999)}")
EOF
```

## Bot Commands Reference

### Available Commands

- `/start` or `/help` — Show help and usage
- `/summarize <URL>` — Summarize URL immediately
- `/summarize` — Bot asks for URL in next message
- `/summarize_all <URLs>` — Process multiple URLs without confirmation
- `/cancel` — Cancel pending operation

### Command Processing

See `app/adapters/telegram/command_processor.py`:

- Commands are defined in `app/adapters/telegram/commands.py`
- Routing logic in `app/adapters/telegram/message_router.py`
- State management in `app/adapters/telegram/task_manager.py`

## Testing Workflows End-to-End

### 1. URL Flow (Complete Pipeline)

```bash
# Run full pipeline
python -m app.cli.summary \
  --url https://example.com/article \
  --json-path test_output.json \
  --log-level DEBUG

# Check output
cat test_output.json | python -m json.tool

# Verify in database
sqlite3 ./data/app.db << EOF
.mode column
.headers on
SELECT id, type, status, input_url
FROM requests
ORDER BY created_at DESC
LIMIT 1;
EOF
```

### 2. Multiple URLs

```bash
python -m app.cli.summary \
  --url "https://example.com/1 https://example.com/2" \
  --accept-multiple \
  --log-level INFO
```

### 3. Error Handling

```bash
# Test with invalid URL
python -m app.cli.summary --url "not-a-url"

# Test with unreachable URL
python -m app.cli.summary --url "https://thisurldoesnotexist12345.com"

# Check error in database
sqlite3 ./data/app.db "
  SELECT id, status, input_url
  FROM requests
  WHERE status = 'error'
  ORDER BY created_at DESC
  LIMIT 5;
"
```

## Running the Full Bot

### Local Development

```bash
# Create virtual environment
make venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Run bot
python bot.py
```

### Docker

```bash
# Build image
docker build -t bite-size-reader .

# Run container
docker run --env-file .env \
  -v $(pwd)/data:/data \
  --name bsr \
  bite-size-reader
```

### Check Bot Health

```bash
# View logs
docker logs bsr

# Check if bot is running
docker ps | grep bsr

# Inspect database
docker exec bsr sqlite3 /data/app.db ".tables"
```

## Integration Tests

### Unit Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_url_utils.py -v

# Run with coverage
python -m pytest tests/ --cov=app --cov-report=html
```

### E2E Tests (Gated)

```bash
# Enable E2E tests
export E2E=1

# Run E2E tests (requires live API keys)
python -m pytest tests/ -v -m integration
```

## Debugging Tips

### 1. Enable Verbose Logging

```bash
export LOG_LEVEL=DEBUG
export DEBUG_PAYLOADS=1
```

### 2. Check Correlation IDs

Every request generates a unique correlation ID:

```bash
# Find in logs
grep "correlation_id" logs/*.log

# Query database
sqlite3 ./data/app.db "SELECT * FROM requests WHERE id = '<cid>';"
```

### 3. Inspect Message Snapshots

```bash
sqlite3 ./data/app.db << EOF
.mode json
SELECT telegram_raw_json
FROM telegram_messages
WHERE request_id = '<correlation_id>';
EOF
```

### 4. Test Prompts

LLM prompts are in `app/prompts/`:

- `en/summary.txt` — English summary prompt
- `ru/summary.txt` — Russian summary prompt

Test prompt changes with CLI runner before deploying.

## Reference Files

- **CLI Runner**: `app/cli/summary.py`
- **Message Handler**: `app/adapters/telegram/message_handler.py`
- **Message Router**: `app/adapters/telegram/message_router.py`
- **URL Handler**: `app/adapters/telegram/url_handler.py`
- **Command Processor**: `app/adapters/telegram/command_processor.py`
- **Access Controller**: `app/adapters/telegram/access_controller.py`

## Important Notes

- CLI runner does NOT send actual Telegram messages
- Stub credentials are auto-generated for local testing
- Database operations work exactly like production
- All validation logic is the same as the live bot
- Use correlation IDs to trace requests across logs and DB
- Test both English and Russian language flows
