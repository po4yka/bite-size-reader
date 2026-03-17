"""Infrastructure and adapter data models for the bite-size-reader application.

Boundary rule: this package contains Pydantic/dataclass models used as data
transfer objects for infrastructure concerns — Telegram message types, LLM
configuration, batch processing payloads, and API data shapes.

These models may reference external library types (Pydantic, StrEnum) and can
depend on adapter-layer types. They are NOT pure domain entities.

For pure domain entities (Request, Summary, User identity), use app/domain/models/.
"""
