"""Domain model entities for the ratatoskr bounded context.

Boundary rule: this package contains pure domain entities and value objects
with no infrastructure dependencies (no ORM, no Pydantic, no external types).
Domain models express business concepts: Request, Summary, User identity.

For infrastructure/adapter data shapes (Telegram types, LLM configs, batch
processing payloads), use app/adapter_models/ instead.
"""
