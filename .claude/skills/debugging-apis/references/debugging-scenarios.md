# Common Debugging Scenarios

## 1. "Firecrawl returns empty content"

Check:

```bash
# View raw response
sqlite3 /data/app.db "
  SELECT raw_response_json
  FROM crawl_results
  WHERE request_id = '<correlation_id>';
" | python -m json.tool

# Check if PDF parser needed
grep -r "parsers.*pdf" app/adapters/content/
```

## 2. "LLM returns invalid JSON"

Check `app/core/json_utils.py`:

- Uses `json_repair` library to fix malformed output
- Falls back through multiple parsing strategies
- Logs repair attempts with correlation ID

## 3. "Rate limit errors"

```bash
# Count recent API calls
sqlite3 /data/app.db "
  SELECT COUNT(*) as calls_last_hour
  FROM llm_calls
  WHERE created_at > datetime('now', '-1 hour');
"
```

## 4. "High API costs"

```bash
# Analyze token usage and costs
sqlite3 /data/app.db << EOF
.mode column
.headers on
SELECT
  model,
  COUNT(*) as calls,
  AVG(tokens_prompt) as avg_prompt,
  AVG(tokens_completion) as avg_completion,
  SUM(cost_usd) as total_cost
FROM llm_calls
WHERE status = 'ok'
GROUP BY model
ORDER BY total_cost DESC;
EOF
```
