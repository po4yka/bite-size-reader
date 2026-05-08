---
title: Rotate OpenRouter providers before advancing to the next fallback model
status: backlog
area: llm
priority: medium
owner: TBD
blocks: []
blocked_by: []
created: 2026-05-08
updated: 2026-05-08
---

- [ ] #task Rotate OpenRouter providers before advancing to the next fallback model #repo/ratatoskr #area/llm #status/backlog 🔽

## Problem

When OpenRouter returns a provider-specific rejection (detected via `error_handler.is_provider_specific_rejection` — metadata.provider_name is set), the current code immediately advances to the next model in the fallback chain. However the rejection is provider-specific (content policy, quota exhaustion, format incompatibility with that provider's version of the model), not model-specific. Another OpenRouter provider serving the same model may accept the identical request. Advancing the model wastes a capable model slot and increases cost by introducing stronger models earlier than necessary.

## Proposed approach

- Track tried providers per (request, model) pair within the request lifecycle; store as a mutable set threaded through the retry loop.
- When `is_provider_specific_rejection` is True and untried providers remain for the current model, retry the current model with an updated `provider_order` header that excludes the failed provider.
- Only advance to the next model in the fallback chain after all available providers for the current model have been exhausted.
- Expose `MODEL_ROUTING_MAX_PROVIDER_ROTATIONS` env var (default: 2) to cap provider rotation attempts per model.
- Log each provider rotation event with the excluded provider name and `correlation_id`.

## Open questions

- Does the OpenRouter API surface a list of available providers per model at request time, or must we maintain a static provider allow-list?
- How should the code determine "no more providers to try" — after N rotations, or by checking a known provider list?
- Does provider rotation interact with the `provider_order` field already in `OpenRouterConfig`? Must ensure the two mechanisms compose correctly.

## Files to touch

- `app/adapters/openrouter/error_handler.py`
- `app/adapters/openrouter/openrouter_client.py`
- `app/adapters/openrouter/request_builder.py` (provider_order header construction)
- `app/config/llm.py` (new max_provider_rotations field)
