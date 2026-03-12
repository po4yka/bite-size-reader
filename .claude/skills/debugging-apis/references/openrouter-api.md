# OpenRouter API Reference

## Endpoints

- **Base URL**: `https://openrouter.ai`
- **Chat completions**: `POST /api/v1/chat/completions`

## Official Documentation

- **Overview**: https://openrouter.ai/docs/api-reference/overview
- **Chat Completions**: https://openrouter.ai/docs/api-reference/chat-completion
- **Quickstart**: https://openrouter.ai/docs/quickstart

## Integration Location

- **Client**: `app/adapters/openrouter/openrouter_client.py`
- **Request Builder**: `app/adapters/openrouter/request_builder.py`
- **Response Processor**: `app/adapters/openrouter/response_processor.py`
- **Error Handler**: `app/adapters/openrouter/error_handler.py`
- **DB Storage**: `llm_calls` table

## Common Request Format

```json
{
  "model": "openai/gpt-4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant..."},
    {"role": "user", "content": "Summarize this article..."}
  ],
  "temperature": 0.3,
  "response_format": {"type": "json_object"}
}
```

## Debugging Failed LLM Calls

```bash
sqlite3 /data/app.db << EOF
.mode json
SELECT
  id,
  model,
  status,
  tokens_prompt,
  tokens_completion,
  cost_usd,
  latency_ms,
  error_text,
  created_at
FROM llm_calls
WHERE request_id = '<correlation_id>'
ORDER BY created_at;
EOF
```

## View Full Request/Response

```bash
# Get request messages
sqlite3 /data/app.db "
  SELECT request_messages_json
  FROM llm_calls
  WHERE request_id = '<correlation_id>'
  LIMIT 1;
" | python -m json.tool

# Get response
sqlite3 /data/app.db "
  SELECT response_json
  FROM llm_calls
  WHERE request_id = '<correlation_id>'
  LIMIT 1;
" | python -m json.tool
```

## Common Error Codes

- **400**: Invalid request (malformed JSON, bad parameters)
- **401**: Invalid API key
- **402**: Insufficient credits
- **429**: Rate limit exceeded
- **500/502/503**: OpenRouter server errors (retry with backoff)
- **Context length exceeded**: Prompt too long for model

## Model Fallback Chain

Check `app/adapters/openrouter/error_handler.py`:

- Primary model configured in `OPENROUTER_MODEL`
- Fallback cascade for structured output failures
- Long-context model support for large articles

## Enable Debug Payloads

```bash
export DEBUG_PAYLOADS=1
export LOG_LEVEL=DEBUG
# Payloads logged with Authorization redacted
```

## Test OpenRouter Directly

```bash
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: $OPENROUTER_HTTP_REFERER" \
  -H "X-Title: $OPENROUTER_X_TITLE" \
  -d '{
    "model": "openai/gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, world!"}
    ]
  }' | python -m json.tool
```
