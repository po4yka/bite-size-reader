---
title: Document and end-to-end-test direct Anthropic / OpenAI / Ollama LLM providers
status: backlog
area: llm
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Document and end-to-end-test direct Anthropic / OpenAI / Ollama LLM providers #repo/ratatoskr #area/llm #status/backlog 🔼

## Objective

`app/adapters/llm/factory.py:23` declares `VALID_PROVIDERS = {"openrouter", "openai", "anthropic", "ollama"}` and the `_create_*` branches exist at lines 82-161 (`anthropic/client.py`, `openai/client.py` already implemented). But README and CLAUDE.md only document OpenRouter, and there are no docs or e2e tests covering the direct paths. Closing this gap unlocks Anthropic 1h prompt caching, Gemini explicit-cache, direct-API cost savings, and regulatory-residency choices — without changing the adapter.

## Context

- Factory: `app/adapters/llm/factory.py:23, :82-161`.
- Existing direct clients: `app/adapters/llm/anthropic/client.py`, `app/adapters/llm/openai/client.py`.
- `app/config/llm.py:97` already hints at provider-specific cache settings.
- README + CLAUDE.md describe only `OPENROUTER_*` env vars.

## Scope

- Document `LLM_PROVIDER=anthropic|openai|ollama` end-to-end: - `docs/reference/environment-variables.md` with each provider block. - `docs/guides/configure-llm-provider.md` (new) explaining the tradeoffs (cost, latency, caching, residency).
- Add per-provider e2e tests exercising `chat_structured` against recorded fixtures (no live API calls in CI).
- Provider-parity table in `docs/reference/llm-providers.md`: feature support (structured output, caching, vision, streaming, JSON mode).
- Cost / latency parity recommendations.

## Acceptance criteria

- [ ] Each of `LLM_PROVIDER=openrouter|anthropic|openai|ollama` starts the bot cleanly and serves a summary roundtrip.
- [ ] At least one e2e test per provider exists and passes.
- [ ] New guide + provider-parity table published.
- [ ] CLAUDE.md updated to mention the alternative providers.

## References

- Factory: `app/adapters/llm/factory.py:23, :82-161`
- Direct clients: `app/adapters/llm/anthropic/client.py`, `app/adapters/llm/openai/client.py`
- LLM config: `app/config/llm.py:97`
