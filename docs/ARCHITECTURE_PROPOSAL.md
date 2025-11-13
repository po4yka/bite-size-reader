# Architecture Proposal for Bite-Size Reader

## Executive Summary

This document proposes a **Hexagonal Architecture (Ports & Adapters)** with layered organization for the Bite-Size Reader project. This architecture addresses the current issues with tight coupling, large god objects, and unclear boundaries while providing a clear migration path from the existing codebase.

## Table of Contents

1. [Current Architecture Issues](#current-architecture-issues)
2. [Proposed Architecture](#proposed-architecture)
3. [Layer Definitions](#layer-definitions)
4. [Component Structure](#component-structure)
5. [Migration Strategy](#migration-strategy)
6. [Benefits](#benefits)
7. [Implementation Roadmap](#implementation-roadmap)

## Current Architecture Issues

### Identified Problems

1. **God Objects**: Database (1888 lines), MessageRouter (1266 lines), LLMSummarizer (1522 lines)
2. **Tight Coupling**: Direct instantiation and concrete dependencies throughout
3. **Mixed Concerns**: Business logic mixed with infrastructure and presentation
4. **Unclear Boundaries**: No clear separation between layers
5. **Difficult Testing**: Hard to test components in isolation
6. **Low Cohesion**: Classes with multiple responsibilities

### Current Strengths

1. **Good Domain Concepts**: Clear concepts like Request, Summary, CrawlResult
2. **Async-First Design**: Proper use of asyncio throughout
3. **Adapter Pattern Started**: `adapters/` directory shows awareness of boundaries
4. **Comprehensive Error Handling**: Good error tracking and logging

## Proposed Architecture

### Hexagonal Architecture with Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                        │
│                     (Telegram Bot Interface)                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ TelegramBot │ MessageRouter │ CommandHandlers │ Formatters │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Uses
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Application Layer                          │
│                  (Use Cases / Business Workflows)                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ SummarizeUrlUseCase │ ProcessForwardUseCase                 │ │
│  │ SearchTopicsUseCase │ ManageReadStatusUseCase               │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Uses
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Domain Layer                            │
│                    (Core Business Logic)                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Domain Models: Request, Summary, Article                    │ │
│  │ Domain Services: SummaryGenerator, MetadataExtractor        │ │
│  │ Domain Events: SummaryCreated, RequestFailed                │ │
│  │ Ports (Interfaces): ISummaryRepository, ILLMClient          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Implemented by
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                        │
│              (External Services & Data Persistence)              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Adapters:                                                    │ │
│  │ - SQLiteRepository (implements ISummaryRepository)          │ │
│  │ - OpenRouterClient (implements ILLMClient)                  │ │
│  │ - FirecrawlClient (implements IContentFetcher)              │ │
│  │ - TopicSearchIndex (implements ISearchService)              │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Dependency Rule**: Dependencies point inward (Presentation → Application → Domain)
2. **Port & Adapter**: Domain defines interfaces (ports), infrastructure implements them (adapters)
3. **Separation of Concerns**: Each layer has a single, clear responsibility
4. **Testability**: Each layer can be tested independently with test doubles

## Layer Definitions

### 1. Domain Layer (Core)

**Responsibility**: Contains business logic independent of frameworks, databases, and UI.

**Location**: `app/domain/`

**Components**:

```
app/domain/
├── models/
│   ├── __init__.py
│   ├── request.py          # Domain model for content requests
│   ├── summary.py          # Domain model for summaries
│   ├── article.py          # Domain model for articles
│   └── user.py             # Domain model for users
├── services/
│   ├── __init__.py
│   ├── summary_generator.py    # Core summarization logic
│   ├── metadata_extractor.py   # Metadata extraction logic
│   └── content_validator.py    # Content validation rules
├── ports/
│   ├── __init__.py
│   ├── repositories.py     # Repository interfaces (already created!)
│   ├── clients.py          # External service interfaces
│   └── events.py           # Event publisher interface
├── events/
│   ├── __init__.py
│   ├── summary_events.py   # Summary-related domain events
│   └── request_events.py   # Request-related domain events
└── exceptions/
    ├── __init__.py
    └── domain_exceptions.py    # Domain-specific exceptions
```

**Key Concepts**:

- **Domain Models**: Rich objects with behavior, not anemic data classes
- **Domain Services**: Business logic that doesn't belong to a single entity
- **Ports (Interfaces)**: Define contracts for external dependencies
- **Domain Events**: Communicate state changes without coupling

**Example Domain Model**:

```python
# app/domain/models/summary.py
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass
class Summary:
    """Domain model for content summary.

    Contains business logic and validation rules.
    """
    id: int | None
    request_id: int
    content: dict
    language: str
    created_at: datetime
    is_read: bool = False

    def mark_as_read(self) -> None:
        """Mark this summary as read."""
        if self.is_read:
            raise ValueError("Summary is already marked as read")
        self.is_read = True

    def validate_content(self) -> bool:
        """Validate summary content completeness."""
        required_fields = ["tldr", "summary_250", "key_ideas"]
        return all(
            field in self.content and self.content[field]
            for field in required_fields
        )

    def get_reading_time_minutes(self) -> int:
        """Calculate estimated reading time."""
        return self.content.get("estimated_reading_time_min", 0)
```

### 2. Application Layer (Use Cases)

**Responsibility**: Orchestrates domain objects and coordinates workflows.

**Location**: `app/application/`

**Components**:

```
app/application/
├── use_cases/
│   ├── __init__.py
│   ├── summarize_url.py        # Summarize URL workflow
│   ├── process_forward.py      # Process forwarded message
│   ├── search_topics.py        # Search for topics
│   ├── manage_read_status.py   # Mark summaries as read/unread
│   └── batch_process.py        # Batch processing workflow
├── commands/
│   ├── __init__.py
│   ├── create_summary.py       # Command for creating summary
│   └── update_read_status.py   # Command for updating status
├── queries/
│   ├── __init__.py
│   ├── get_summary.py          # Query for getting summaries
│   └── search_topics.py        # Query for searching topics
└── dto/
    ├── __init__.py
    ├── summary_dto.py          # Data transfer objects
    └── request_dto.py
```

**Key Concepts**:

- **Use Cases**: Single-purpose application workflows
- **Commands**: Write operations that change state (CQRS pattern)
- **Queries**: Read operations that retrieve data (CQRS pattern)
- **DTOs**: Simple data structures for transferring data between layers

**Example Use Case**:

```python
# app/application/use_cases/summarize_url.py
from dataclasses import dataclass
from typing import Protocol

from app.domain.models.request import Request
from app.domain.models.summary import Summary
from app.domain.ports.repositories import ISummaryRepository, IRequestRepository
from app.domain.ports.clients import ILLMClient, IContentFetcher
from app.domain.services.summary_generator import SummaryGenerator


@dataclass
class SummarizeUrlCommand:
    """Command for summarizing a URL."""
    url: str
    user_id: int
    chat_id: int
    language: str | None = None


class SummarizeUrlUseCase:
    """Use case for summarizing a URL.

    Orchestrates the workflow of fetching content, generating summary,
    and persisting results.
    """

    def __init__(
        self,
        request_repo: IRequestRepository,
        summary_repo: ISummaryRepository,
        content_fetcher: IContentFetcher,
        llm_client: ILLMClient,
        summary_generator: SummaryGenerator,
    ) -> None:
        self._request_repo = request_repo
        self._summary_repo = summary_repo
        self._content_fetcher = content_fetcher
        self._llm_client = llm_client
        self._summary_generator = summary_generator

    async def execute(self, command: SummarizeUrlCommand) -> Summary:
        """Execute the summarization workflow."""
        # 1. Create request record
        request = await self._request_repo.create(
            user_id=command.user_id,
            chat_id=command.chat_id,
            url=command.url,
        )

        try:
            # 2. Fetch content
            content = await self._content_fetcher.fetch(command.url)

            # 3. Generate summary using domain service
            summary = await self._summary_generator.generate(
                content=content,
                language=command.language,
                llm_client=self._llm_client,
            )

            # 4. Associate with request
            summary.request_id = request.id

            # 5. Persist summary
            saved_summary = await self._summary_repo.save(summary)

            # 6. Update request status
            await self._request_repo.update_status(request.id, "completed")

            return saved_summary

        except Exception as e:
            # Handle errors and update request status
            await self._request_repo.update_status(request.id, "failed")
            raise
```

### 3. Infrastructure Layer (Adapters)

**Responsibility**: Implements ports defined by domain, handles external services.

**Location**: `app/infrastructure/`

**Components**:

```
app/infrastructure/
├── persistence/
│   ├── __init__.py
│   ├── sqlite/
│   │   ├── __init__.py
│   │   ├── connection.py       # Database connection management
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── summary_repository.py   # ISummaryRepository implementation
│   │   │   ├── request_repository.py   # IRequestRepository implementation
│   │   │   └── user_repository.py      # IUserRepository implementation
│   │   └── models.py           # ORM models (Peewee)
│   └── cache/
│       └── redis_cache.py      # Optional caching layer
├── clients/
│   ├── __init__.py
│   ├── openrouter/
│   │   ├── __init__.py
│   │   ├── client.py           # ILLMClient implementation
│   │   └── config.py
│   ├── firecrawl/
│   │   ├── __init__.py
│   │   ├── client.py           # IContentFetcher implementation
│   │   └── config.py
│   └── search/
│       ├── __init__.py
│       └── topic_search.py     # ISearchService implementation
└── messaging/
    ├── __init__.py
    └── event_bus.py            # Simple in-memory event bus
```

**Key Concepts**:

- **Repository Implementations**: Translate domain models to/from database
- **Client Implementations**: Wrap external APIs
- **No Business Logic**: Pure translation and communication

**Example Repository**:

```python
# app/infrastructure/persistence/sqlite/repositories/summary_repository.py
from typing import Optional
import asyncio

from app.domain.models.summary import Summary
from app.domain.ports.repositories import ISummaryRepository
from app.infrastructure.persistence.sqlite.models import SummaryModel


class SqliteSummaryRepository(ISummaryRepository):
    """SQLite implementation of summary repository."""

    def __init__(self, db_lock: asyncio.Lock) -> None:
        self._lock = db_lock

    async def save(self, summary: Summary) -> Summary:
        """Save summary to database."""
        async with self._lock:
            # Translate domain model to ORM model
            db_model = SummaryModel.create(
                request_id=summary.request_id,
                json_payload=summary.content,
                lang=summary.language,
                is_read=summary.is_read,
            )

            # Translate back to domain model with ID
            return Summary(
                id=db_model.id,
                request_id=summary.request_id,
                content=summary.content,
                language=summary.language,
                created_at=db_model.created_at,
                is_read=summary.is_read,
            )

    async def get_by_id(self, summary_id: int) -> Optional[Summary]:
        """Get summary by ID."""
        async with self._lock:
            try:
                db_model = SummaryModel.get_by_id(summary_id)
                return self._to_domain(db_model)
            except SummaryModel.DoesNotExist:
                return None

    def _to_domain(self, db_model: SummaryModel) -> Summary:
        """Convert ORM model to domain model."""
        return Summary(
            id=db_model.id,
            request_id=db_model.request_id,
            content=db_model.json_payload,
            language=db_model.lang,
            created_at=db_model.created_at,
            is_read=db_model.is_read,
        )
```

### 4. Presentation Layer (Interface)

**Responsibility**: Handles user interaction, formats output, routes commands.

**Location**: `app/presentation/` (or keep as `app/adapters/telegram/`)

**Components**:

```
app/presentation/telegram/
├── __init__.py
├── bot.py                  # Main bot initialization
├── handlers/
│   ├── __init__.py
│   ├── command_handler.py  # Command routing (using Command Pattern)
│   ├── message_handler.py  # Message routing
│   └── callback_handler.py # Callback query handling
├── commands/
│   ├── __init__.py
│   ├── start_command.py    # /start command handler
│   ├── help_command.py     # /help command handler
│   ├── summarize_command.py # /summarize command handler
│   └── search_command.py   # /find command handler
├── formatters/
│   ├── __init__.py
│   ├── summary_formatter.py    # Format summaries for display
│   ├── error_formatter.py      # Format error messages
│   └── progress_formatter.py   # Format progress updates
└── middleware/
    ├── __init__.py
    ├── rate_limiter.py     # Rate limiting middleware
    ├── auth.py             # Authorization middleware
    └── logging.py          # Logging middleware
```

**Key Concepts**:

- **Thin Layer**: Minimal logic, delegates to use cases
- **Formatting Only**: Handles presentation concerns
- **Input Validation**: Basic validation before passing to use cases
- **Error Translation**: Converts domain exceptions to user-friendly messages

**Example Command Handler**:

```python
# app/presentation/telegram/commands/summarize_command.py
from pyrogram import Client
from pyrogram.types import Message

from app.application.use_cases.summarize_url import (
    SummarizeUrlUseCase,
    SummarizeUrlCommand,
)
from app.presentation.telegram.formatters.summary_formatter import SummaryFormatter
from app.presentation.telegram.formatters.error_formatter import ErrorFormatter


class SummarizeCommandHandler:
    """Handler for /summarize command."""

    def __init__(
        self,
        use_case: SummarizeUrlUseCase,
        summary_formatter: SummaryFormatter,
        error_formatter: ErrorFormatter,
    ) -> None:
        self._use_case = use_case
        self._summary_formatter = summary_formatter
        self._error_formatter = error_formatter

    async def handle(self, client: Client, message: Message) -> None:
        """Handle /summarize command."""
        # Extract URL from message
        url = self._extract_url(message.text)
        if not url:
            await message.reply("Please provide a URL to summarize.")
            return

        # Show progress
        status_msg = await message.reply("🔄 Fetching content...")

        try:
            # Execute use case
            command = SummarizeUrlCommand(
                url=url,
                user_id=message.from_user.id,
                chat_id=message.chat.id,
            )
            summary = await self._use_case.execute(command)

            # Format and send result
            formatted = self._summary_formatter.format(summary)
            await status_msg.edit(formatted)

        except Exception as e:
            # Format error for user
            error_msg = self._error_formatter.format(e)
            await status_msg.edit(error_msg)

    def _extract_url(self, text: str) -> str | None:
        """Extract URL from command text."""
        # Simple extraction logic
        parts = text.split(maxsplit=1)
        return parts[1] if len(parts) > 1 else None
```

## Component Structure

### Dependency Injection

Use a dependency injection container to wire components:

```python
# app/di/container.py
from dataclasses import dataclass
import asyncio

from app.domain.services.summary_generator import SummaryGenerator
from app.application.use_cases.summarize_url import SummarizeUrlUseCase
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepository,
)
from app.infrastructure.clients.openrouter.client import OpenRouterClient
from app.config import AppConfig


@dataclass
class Container:
    """Dependency injection container."""

    config: AppConfig
    db_lock: asyncio.Lock

    # Repositories (lazy initialization)
    _summary_repo: SqliteSummaryRepository | None = None
    _request_repo: SqliteRequestRepository | None = None

    # Clients (lazy initialization)
    _llm_client: OpenRouterClient | None = None
    _content_fetcher: FirecrawlClient | None = None

    # Services (lazy initialization)
    _summary_generator: SummaryGenerator | None = None

    # Use Cases (lazy initialization)
    _summarize_url_use_case: SummarizeUrlUseCase | None = None

    @property
    def summary_repo(self) -> SqliteSummaryRepository:
        """Get or create summary repository."""
        if self._summary_repo is None:
            self._summary_repo = SqliteSummaryRepository(self.db_lock)
        return self._summary_repo

    @property
    def llm_client(self) -> OpenRouterClient:
        """Get or create LLM client."""
        if self._llm_client is None:
            self._llm_client = OpenRouterClient(self.config.openrouter)
        return self._llm_client

    @property
    def summary_generator(self) -> SummaryGenerator:
        """Get or create summary generator."""
        if self._summary_generator is None:
            self._summary_generator = SummaryGenerator()
        return self._summary_generator

    @property
    def summarize_url_use_case(self) -> SummarizeUrlUseCase:
        """Get or create summarize URL use case."""
        if self._summarize_url_use_case is None:
            self._summarize_url_use_case = SummarizeUrlUseCase(
                request_repo=self.request_repo,
                summary_repo=self.summary_repo,
                content_fetcher=self.content_fetcher,
                llm_client=self.llm_client,
                summary_generator=self.summary_generator,
            )
        return self._summarize_url_use_case
```

### CQRS Pattern (Optional Enhancement)

For better scalability, consider separating reads and writes:

```
app/application/
├── commands/           # Write operations
│   ├── create_summary_command.py
│   └── update_read_status_command.py
└── queries/           # Read operations
    ├── get_summary_query.py
    └── search_topics_query.py
```

**Benefits**:
- Optimize reads and writes independently
- Clearer separation of concerns
- Better performance for complex queries
- Easier to add read models/views

## Migration Strategy

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Establish new structure without breaking existing code

1. ✅ **Create protocols** (Already done!)
2. ✅ **Create repository adapters** (Already done!)
3. **Create domain models**:
   - Extract `Request`, `Summary`, `Article` from database models
   - Add business logic methods
4. **Set up directory structure**:
   - Create `app/domain/`, `app/application/`, `app/infrastructure/`
   - Keep existing code in place

### Phase 2: Extract Use Cases (Weeks 3-4)

**Goal**: Move business logic into use cases

1. **Identify workflows** in current code:
   - URL summarization
   - Forward processing
   - Topic search
   - Read status management
2. **Create use case classes**:
   - `SummarizeUrlUseCase`
   - `ProcessForwardUseCase`
   - `SearchTopicsUseCase`
3. **Update handlers** to call use cases instead of direct logic

### Phase 3: Refactor Infrastructure (Weeks 5-6)

**Goal**: Move infrastructure concerns to infrastructure layer

1. **Split Database class**:
   - Move request operations to `RequestRepositoryImpl`
   - Move summary operations to `SummaryRepositoryImpl`
   - Keep Database as facade for backward compatibility
2. **Organize clients**:
   - Move OpenRouterClient to `infrastructure/clients/openrouter/`
   - Move FirecrawlClient to `infrastructure/clients/firecrawl/`
3. **Update all references** to use new locations

### Phase 4: Apply Command Pattern (Week 7)

**Goal**: Make command routing extensible

1. **Set up CommandRegistry** in MessageRouter
2. **Convert command handlers** to Command classes
3. **Register all commands**
4. **Remove if/elif chain**, use registry exclusively

### Phase 5: Dependency Injection (Week 8)

**Goal**: Eliminate direct instantiation

1. **Create Container class**
2. **Wire dependencies** in container
3. **Update TelegramBot** to use container
4. **Remove direct instantiation** from __init__ methods

### Phase 6: Testing & Documentation (Weeks 9-10)

**Goal**: Ensure quality and knowledge transfer

1. **Add unit tests** for domain services
2. **Add integration tests** for use cases
3. **Update documentation**
4. **Create migration guide** for future developers

## Benefits

### Immediate Benefits

1. **Testability**: Each layer can be tested independently
2. **Clarity**: Clear boundaries and responsibilities
3. **Flexibility**: Easy to swap implementations
4. **Maintainability**: Changes localized to single layer

### Long-term Benefits

1. **Scalability**: Easy to add new features
2. **Team Productivity**: Clear structure for team collaboration
3. **Code Quality**: Enforced separation prevents coupling
4. **Migration Path**: Easy to migrate to microservices if needed

### Specific to Your Project

1. **Fixes God Objects**: Each layer has focused classes
2. **Enables Testing**: Mock external dependencies easily
3. **Better Async**: Clear async boundaries between layers
4. **Concurrent Safety**: Proper synchronization at infrastructure layer

## Implementation Roadmap

### Immediate Next Steps (This Week)

1. **Create domain models**:
   ```bash
   mkdir -p app/domain/models
   # Create Request, Summary, Article domain models
   ```

2. **Create first use case**:
   ```bash
   mkdir -p app/application/use_cases
   # Extract SummarizeUrlUseCase from existing code
   ```

3. **Update one handler** to use new structure as proof of concept

### Month 1: Foundation

- Week 1: Domain layer setup
- Week 2: Application layer setup
- Week 3: First use case migration
- Week 4: Infrastructure reorganization

### Month 2: Migration

- Week 5-6: Split Database class
- Week 7: Apply Command Pattern
- Week 8: Dependency Injection

### Month 3: Polish

- Week 9: Testing
- Week 10: Documentation
- Week 11-12: Performance optimization

## Conclusion

This architecture provides:

- ✅ **Clear separation of concerns**
- ✅ **Testable components**
- ✅ **Flexible infrastructure**
- ✅ **Extensible command system**
- ✅ **Migration path from current code**

The protocols and repositories already created provide the foundation. The next step is to create domain models and begin extracting use cases.

This architecture will make the codebase more maintainable, testable, and ready for growth.
