"""Canonical namespace for adapter and infrastructure data models.

Use this package for Pydantic/dataclass models that are shared across multiple
adapters (e.g. LLM request/response models used by both OpenRouter and Anthropic
clients, batch processing DTOs consumed by multiple services).

Types owned by a single adapter belong in ``app/adapters/<name>/`` alongside
the adapter that produces them. Pure business entities live in ``app.domain``.
"""
