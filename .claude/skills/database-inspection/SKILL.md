---
name: database-inspection
description: Query and inspect SQLite database for debugging requests, summaries, crawl results, and LLM calls. Use when investigating issues with correlation IDs or analyzing stored data.
version: 1.0.0
allowed-tools: Bash, Read
---

# Database Inspection Skill

Helps query and inspect the Bite-Size Reader SQLite database for debugging and analysis.

## Database Location

- **Default path**: `/data/app.db`
- **Check env**: `DB_PATH` environment variable
- **Local dev**: Usually `./data/app.db` in project root

## Common Query Patterns

### Find Request by Correlation ID

```bash
sqlite3 /data/app.db "SELECT * FROM requests WHERE id = '<correlation_id>';"
```

### Check Recent Requests

```bash
sqlite3 /data/app.db "SELECT id, type, status, input_url, created_at FROM requests ORDER BY created_at DESC LIMIT 10;"
```

### Find Failed Requests

```bash
sqlite3 /data/app.db "SELECT id, type, status, input_url, created_at FROM requests WHERE status = 'error' ORDER BY created_at DESC LIMIT 20;"
```

### Check Crawl Results for URL

```bash
sqlite3 /data/app.db "SELECT request_id, source_url, status, firecrawl_success, firecrawl_error_message, http_status FROM crawl_results WHERE request_id = '<correlation_id>';"
```

### View LLM Calls for Request

```bash
sqlite3 /data/app.db "SELECT id, model, status, tokens_prompt, tokens_completion, cost_usd, error_text FROM llm_calls WHERE request_id = '<correlation_id>';"
```

### Check Summary Output

```bash
sqlite3 /data/app.db "SELECT request_id, lang, json_payload, version FROM summaries WHERE request_id = '<correlation_id>';"
```

### View Telegram Message Snapshot

```bash
sqlite3 /data/app.db "SELECT message_id, chat_id, text_full, forward_from_chat_title FROM telegram_messages WHERE request_id = '<correlation_id>';"
```

### List All Tables

```bash
sqlite3 /data/app.db ".tables"
```

### Show Table Schema

```bash
sqlite3 /data/app.db ".schema requests"
sqlite3 /data/app.db ".schema crawl_results"
sqlite3 /data/app.db ".schema llm_calls"
sqlite3 /data/app.db ".schema summaries"
```

### Count Records by Type

```bash
sqlite3 /data/app.db "SELECT type, COUNT(*) as count FROM requests GROUP BY type;"
```

### Success Rate Statistics

```bash
sqlite3 /data/app.db "SELECT status, COUNT(*) as count FROM requests GROUP BY status;"
```

### Average Token Usage

```bash
sqlite3 /data/app.db "SELECT AVG(tokens_prompt) as avg_prompt, AVG(tokens_completion) as avg_completion FROM llm_calls WHERE status = 'ok';"
```

### Total API Costs

```bash
sqlite3 /data/app.db "SELECT SUM(cost_usd) as total_cost FROM llm_calls WHERE cost_usd IS NOT NULL;"
```

## Usage Tips

1. **Format output nicely**:

   ```bash
   sqlite3 /data/app.db << EOF
   .mode column
   .headers on
   SELECT * FROM requests LIMIT 5;
   EOF
   ```

2. **Export to JSON**:

   ```bash
   sqlite3 /data/app.db << EOF
   .mode json
   SELECT * FROM requests WHERE id = '<correlation_id>';
   EOF
   ```

3. **Pretty print JSON payloads**:

   ```bash
   sqlite3 /data/app.db "SELECT json_payload FROM summaries WHERE request_id = '<correlation_id>';" | python -m json.tool
   ```

4. **Search by URL pattern**:

   ```bash
   sqlite3 /data/app.db "SELECT id, input_url, status FROM requests WHERE input_url LIKE '%example.com%';"
   ```

## Important Notes

- Always use correlation IDs for tracing end-to-end flow
- Check both `status` fields and error columns
- LLM calls table stores ALL attempts (including failures)
- Firecrawl responses are in `crawl_results.content_markdown`
- Full Telegram snapshots are in `telegram_raw_json` field
- Authorization headers are redacted before storage

## Schema Reference

**Key tables**: requests, telegram_messages, crawl_results, llm_calls, summaries

See `app/db/models.py` for complete Peewee ORM models.
