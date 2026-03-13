# ADR-0004: Hexagonal Architecture Pattern

**Date:** 2025-01-10

**Status:** Accepted

**Deciders:** po4yka

**Technical Story:** Restructure codebase for testability, maintainability, and future extensibility

## Context

As Bite-Size Reader evolved from a simple Telegram bot to a multi-interface system (Telegram, mobile app, CLI, MCP server), the codebase faced several architectural challenges:

1. **Tight Coupling**: Business logic embedded in Telegram handlers (hard to test without Pyrogram mocks)
2. **External Service Lock-In**: Direct dependencies on Firecrawl and OpenRouter throughout codebase
3. **Testing Difficulty**: Integration tests require full Telegram bot setup
4. **Code Duplication**: Similar logic repeated across Telegram, CLI, and mobile API
5. **Database Leakage**: Peewee ORM models accessed directly from business logic
6. **Interface Proliferation**: Adding new interfaces (gRPC, web UI) would require forking logic

Traditional monolithic architecture problems:

- Business logic tightly coupled to frameworks (Pyrogram, FastAPI, Peewee)
- Hard to swap external services (Firecrawl → custom scraper)
- Difficult to test in isolation (need database, API mocks, Telegram mocks)
- Code organization unclear (where does "summarization logic" live?)

## Decision

We will refactor to **Hexagonal Architecture** (Ports and Adapters):

**Core Principles**:

- **Domain Layer** (`app/domain/`): Pure business logic, no external dependencies
- **Application Layer** (`app/application/`): Use cases and DTOs orchestrating domain logic
- **Adapters** (`app/adapters/`): Interface implementations (Telegram, Firecrawl, OpenRouter, database)
- **Dependency Inversion**: Core depends on abstractions (ports), adapters implement interfaces
- **Framework Independence**: Core logic usable without Pyrogram, FastAPI, or Peewee

**Structure**:

```
app/
├── domain/          # Business entities and domain services (framework-free)
├── application/     # Use cases and DTOs (orchestration layer)
│   ├── dto/         # Data transfer objects
│   └── use_cases/   # Application logic (summarize, search, sync)
├── adapters/        # External integrations
│   ├── telegram/    # Pyrogram bot (input adapter)
│   ├── content/     # Firecrawl, yt-dlp (output adapters)
│   ├── llm/         # OpenRouter, OpenAI (output adapters)
│   └── external/    # Other services
├── infrastructure/  # Persistence, event bus, vector store
└── api/             # FastAPI (input adapter)
```

## Consequences

### Positive

- **Testability**: Core logic testable without Telegram/database mocks (unit tests)
- **Flexibility**: Can swap Firecrawl for custom scraper without changing core logic
- **Reusability**: Same use cases power Telegram, CLI, mobile API, MCP server
- **Clear Boundaries**: Obvious where to put new code (domain vs adapter vs use case)
- **Framework Independence**: Core logic portable to other frameworks (Flask, Discord bot, gRPC)
- **Onboarding**: New developers understand code organization faster
- **Parallel Development**: Teams can work on adapters without touching core logic

### Negative

- **Increased Abstraction**: More files, more indirection (port interfaces, DTOs)
- **Learning Curve**: Developers must understand hexagonal architecture concepts
- **Boilerplate**: DTOs, port interfaces, dependency injection setup
- **Initial Refactoring Cost**: 2-3 weeks to migrate existing code
- **Overkill for Small Projects**: May be over-engineered for single-developer projects
- **Performance Overhead**: DTO mapping adds minor CPU/memory overhead

### Neutral

- Existing code gradually migrated (not big-bang rewrite)
- `app/db/` remains for now (full Repository pattern deferred)
- Dependency injection manual for now (no DI framework like `injector` yet)

## Alternatives Considered

### Alternative 1: Keep Monolithic Structure

Continue with current flat structure (everything in `app/`).

**Pros:**

- Zero refactoring cost
- Simple mental model (all code in one place)
- Fast prototyping (no abstraction overhead)

**Cons:**

- **Tight Coupling**: Business logic mixed with Telegram handlers
- **Hard to Test**: Need full bot setup for unit tests
- **Code Duplication**: Logic repeated across Telegram, CLI, API
- **No Clear Boundaries**: Unclear where new code belongs

**Why not chosen**: Doesn't scale as project grows. Already experiencing pain points (testing, code duplication).

### Alternative 2: Clean Architecture (Uncle Bob)

Adopt full Clean Architecture with strict layer rules and dependency inversion.

**Pros:**

- Even stricter boundaries (entities, use cases, controllers, frameworks)
- Industry-standard pattern (many resources, examples)
- Excellent testability and flexibility

**Cons:**

- **Higher Complexity**: 5+ layers (entities, use cases, gateways, controllers, frameworks)
- **More Boilerplate**: Even more interfaces and DTOs than hexagonal
- **Steeper Learning Curve**: Requires understanding all layers and dependency rules

**Why not chosen**: Hexagonal architecture achieves 80% of benefits with 50% of complexity. Good enough for this project.

### Alternative 3: Domain-Driven Design (DDD) with Aggregates

Apply full DDD with bounded contexts, aggregates, and domain events.

**Pros:**

- Models complex business domains accurately
- Event sourcing enables time-travel debugging
- Aggregates enforce invariants

**Cons:**

- **Overkill**: Bite-Size Reader doesn't have complex domain logic (no multi-entity transactions)
- **Steep Learning Curve**: Requires understanding DDD tactical patterns (aggregates, value objects, repositories)
- **Event Sourcing Overhead**: Need event store, projection rebuilding, eventual consistency

**Why not chosen**: DDD's benefits shine in complex domains (banking, e-commerce). Summarization is too simple to justify DDD complexity.

### Alternative 4: Microservices

Split into separate services (summarization service, search service, Telegram service).

**Pros:**

- Independent deployment and scaling
- Technology diversity (different languages per service)
- Team autonomy (teams own services)

**Cons:**

- **Operational Overhead**: Need Docker Compose, service discovery, inter-service auth
- **Network Latency**: HTTP calls between services (vs in-process function calls)
- **Distributed Debugging**: Tracing across services is hard
- **Overkill**: Single-user deployment doesn't need independent scaling

**Why not chosen**: Microservices solve scaling and team problems we don't have. Monolith with hexagonal architecture is simpler.

## Decision Criteria

1. **Testability** (High): Must enable unit testing without external dependencies
2. **Flexibility** (High): Must support multiple interfaces (Telegram, API, CLI, MCP)
3. **Maintainability** (High): Must clarify code organization and boundaries
4. **Complexity** (Medium): Should balance benefits vs boilerplate
5. **Migration Cost** (Medium): Should allow gradual refactoring (not big-bang)
6. **Performance** (Low): Minor overhead acceptable

Hexagonal architecture scored highest on testability, flexibility, and maintainability.

## Related Decisions

- [ADR-0001](0001-use-firecrawl-for-content-extraction.md) - Firecrawl adapter implements port interface
- [ADR-0005](0005-multi-agent-llm-pipeline.md) - Multi-agent system built on hexagonal foundation
- Future: Full Repository pattern for database (deferred, using Peewee directly for now)

## Implementation Notes

**Key Ports (Interfaces)**:

- `ContentExtractorPort` → Implemented by `FirecrawlAdapter`, `TrafilaturaAdapter`
- `LLMPort` → Implemented by `OpenRouterAdapter`, `OpenAIAdapter`, `AnthropicAdapter`
- `VectorStorePort` → Implemented by `ChromaAdapter`

**Use Cases** (`app/application/use_cases/`):

- `SummarizeContentUseCase` - Orchestrates content extraction + LLM summarization
- `SearchSummariesUseCase` - Orchestrates vector search + reranking
- `SyncSummariesUseCase` - Orchestrates mobile sync logic

**Adapters** (`app/adapters/`):

- **Input Adapters**: `telegram/` (Pyrogram bot), `api/` (FastAPI)
- **Output Adapters**: `content/` (Firecrawl), `llm/` (OpenRouter), `youtube/` (yt-dlp)

**Migration Progress**:

- ✅ Domain models defined (`app/domain/models/`)
- ✅ Use cases extracted (`app/application/use_cases/`)
- ✅ DTOs created (`app/application/dto/`)
- ✅ Adapter interfaces defined (`app/adapters/*/ports.py`)
- 🚧 Repository pattern (partially implemented, using Peewee directly for now)
- 🚧 Full dependency injection (manual wiring for now)

See [HEXAGONAL_ARCHITECTURE_QUICKSTART.md](../HEXAGONAL_ARCHITECTURE_QUICKSTART.md) for implementation guide.

## Notes

**2025-01-10**: Initial migration completed. Core summarization logic now framework-independent.

**2025-02-01**: Mobile API and MCP server built on hexagonal foundation without duplicating logic.

**2026-02-23**: Legacy `app/db/database.py` facade decomposed into focused operation modules (`database_user_ops`, `database_request_ops`, `database_summary_ops`, `database_embedding_media_ops`) to reduce module size while preserving backward compatibility.

**2026-03-13**: Removed the `Database` facade and all 4 mixin modules entirely. `DatabaseSessionManager` (`app/db/session.py`) is now the sole database entry point. Test helpers moved to standalone functions in `tests/db_helpers.py`.

**Future**: Consider `injector` or `dependency-injector` library for automated DI as codebase grows.

---

### Update Log

| Date | Author | Change |
| ------ | -------- | -------- |
| 2025-01-10 | po4yka | Initial decision (Accepted) |
| 2025-02-01 | po4yka | Added mobile API and MCP server note |
| 2026-02-23 | codex | Documented legacy DB facade decomposition into focused operation modules |
| 2026-03-13 | po4yka | Documented removal of Database facade; DatabaseSessionManager is sole DB entry point |
