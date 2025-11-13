# Hexagonal Architecture Quick Start Guide

This guide helps you understand and use the new hexagonal architecture in the Bite-Size Reader project.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [When to Use Each Layer](#when-to-use-each-layer)
3. [Creating a New Feature](#creating-a-new-feature)
4. [Common Patterns](#common-patterns)
5. [Examples](#examples)
6. [Testing](#testing)
7. [FAQs](#faqs)

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  Presentation (Telegram Handlers)       │  ← User interaction
└──────────────────┬──────────────────────┘
                   │ Uses
                   ▼
┌─────────────────────────────────────────┐
│  Application (Use Cases)                │  ← Business workflows
└──────────────────┬──────────────────────┘
                   │ Uses
                   ▼
┌─────────────────────────────────────────┐
│  Domain (Models, Services, Events)      │  ← Core business logic
└──────────────────┬──────────────────────┘
                   │ Implemented by
                   ▼
┌─────────────────────────────────────────┐
│  Infrastructure (Database, APIs)        │  ← External services
└─────────────────────────────────────────┘
```

**Key Rule**: Dependencies point inward. Domain has no dependencies on outer layers.

## When to Use Each Layer

### Domain Layer (`app/domain/`)

**Use for**: Pure business logic that would be the same regardless of technology.

**What goes here**:
- ✅ Business rules and validations
- ✅ Entity behavior (methods that operate on entity data)
- ✅ Domain calculations
- ✅ State machines and transitions
- ✅ Business exceptions

**What does NOT go here**:
- ❌ Database queries
- ❌ API calls
- ❌ Framework-specific code
- ❌ UI/formatting logic
- ❌ Infrastructure concerns

**Example**: "A summary can only be marked as read if it has content" is a business rule → Domain layer.

### Application Layer (`app/application/`)

**Use for**: Orchestrating domain objects to fulfill use cases.

**What goes here**:
- ✅ Use case implementations (workflows)
- ✅ Transaction boundaries
- ✅ Calling multiple repositories
- ✅ Coordinating domain services
- ✅ Application-level validation
- ✅ DTOs for data transfer

**What does NOT go here**:
- ❌ Business rules (those belong in Domain)
- ❌ Database implementation details
- ❌ Presentation formatting
- ❌ Direct database queries

**Example**: "To summarize a URL, fetch content, generate summary, then save it" is a workflow → Application layer.

### Infrastructure Layer (`app/infrastructure/`)

**Use for**: Implementing interfaces defined by Domain using specific technologies.

**What goes here**:
- ✅ Database repositories
- ✅ API clients
- ✅ File system access
- ✅ External service integrations
- ✅ Technology-specific code

**What does NOT go here**:
- ❌ Business logic
- ❌ Workflow orchestration
- ❌ Presentation logic

**Example**: "How to query SQLite database" → Infrastructure layer.

### Presentation Layer (`app/adapters/telegram/`)

**Use for**: Handling user interaction and formatting responses.

**What goes here**:
- ✅ Command handlers
- ✅ Message routing
- ✅ Input parsing
- ✅ Response formatting
- ✅ User error messages

**What does NOT go here**:
- ❌ Business logic
- ❌ Database queries
- ❌ API calls

**Example**: "Format a summary for Telegram display" → Presentation layer.

## Creating a New Feature

### Step 1: Define Domain Model (if needed)

If the feature involves a new entity, create a domain model:

```python
# app/domain/models/article.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Article:
    """Domain model for an article."""

    url: str
    title: str
    content: str
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_valid(self) -> bool:
        """Check if article has minimum required content."""
        return bool(self.title and self.content)

    def get_word_count(self) -> int:
        """Calculate word count of content."""
        return len(self.content.split())
```

**Key points**:
- Use `@dataclass` for simplicity
- Add methods for business logic
- No infrastructure dependencies
- Type hints for all fields

### Step 2: Define Domain Service (if needed)

If you have business logic that doesn't belong to a single entity:

```python
# app/domain/services/article_analyzer.py
class ArticleAnalyzer:
    """Domain service for analyzing articles."""

    @staticmethod
    def calculate_reading_time(article: Article) -> int:
        """Calculate estimated reading time in minutes.

        Business rule: Average reading speed is 200 words per minute.
        """
        word_count = article.get_word_count()
        return max(1, word_count // 200)
```

### Step 3: Create Use Case

Define the workflow in the application layer:

```python
# app/application/use_cases/fetch_article.py
from dataclasses import dataclass

@dataclass
class FetchArticleCommand:
    """Command for fetching an article."""
    url: str
    user_id: int

class FetchArticleUseCase:
    """Use case for fetching and storing an article."""

    def __init__(
        self,
        article_repo: ArticleRepository,
        content_fetcher: IContentFetcher,
    ):
        self._article_repo = article_repo
        self._content_fetcher = content_fetcher

    async def execute(self, command: FetchArticleCommand) -> Article:
        """Execute the fetch article workflow."""
        # 1. Fetch content from URL
        content = await self._content_fetcher.fetch(command.url)

        # 2. Create domain model
        article = Article(
            url=command.url,
            title=content.title,
            content=content.text,
        )

        # 3. Validate (domain logic)
        if not article.is_valid():
            raise ValidationError("Article has insufficient content")

        # 4. Persist (infrastructure)
        saved_article = await self._article_repo.save(article)

        return saved_article
```

**Key points**:
- Command object for input
- Inject dependencies (repositories, clients)
- Orchestrate domain objects
- Clear workflow steps

### Step 4: Create Repository Adapter (if needed)

Implement the repository interface in infrastructure:

```python
# app/infrastructure/persistence/sqlite/repositories/article_repository.py
class SqliteArticleRepository:
    """SQLite implementation of article repository."""

    def __init__(self, database: Any):
        self._db = database

    async def save(self, article: Article) -> Article:
        """Save article to database."""
        # Convert domain model to database format
        db_data = {
            'url': article.url,
            'title': article.title,
            'content': article.content,
        }

        # Call existing database methods
        article_id = await self._db.async_insert_article(**db_data)

        # Return domain model with ID
        article.id = article_id
        return article
```

### Step 5: Wire It Up in Presentation

Update the handler to use the use case:

```python
# app/adapters/telegram/handlers/article_handler.py
class ArticleCommandHandler:
    """Handler for article-related commands."""

    def __init__(self, fetch_article_use_case: FetchArticleUseCase):
        self._fetch_use_case = fetch_article_use_case

    async def handle_fetch(self, message: Message, url: str):
        """Handle article fetch command."""
        try:
            # Create command
            command = FetchArticleCommand(
                url=url,
                user_id=message.from_user.id,
            )

            # Execute use case
            article = await self._fetch_use_case.execute(command)

            # Format response
            response = f"✅ Article fetched: {article.title}"
            await message.reply(response)

        except ValidationError as e:
            await message.reply(f"❌ {e.message}")
```

## Common Patterns

### Pattern 1: Rich Domain Models

**Don't**: Anemic models with just data

```python
# ❌ Bad: Anemic model
@dataclass
class Summary:
    id: int
    content: dict
    is_read: bool
```

**Do**: Rich models with behavior

```python
# ✅ Good: Rich model
@dataclass
class Summary:
    id: int
    content: dict
    is_read: bool

    def mark_as_read(self) -> None:
        """Mark summary as read with validation."""
        if self.is_read:
            raise ValueError("Already read")
        self.is_read = True

    def has_content(self) -> bool:
        """Check if summary has sufficient content."""
        return len(self.content.get('tldr', '')) > 0
```

### Pattern 2: Command Objects

**Don't**: Many parameters in use case methods

```python
# ❌ Bad: Too many parameters
async def execute(self, summary_id: int, user_id: int, chat_id: int, ...):
    pass
```

**Do**: Single command object

```python
# ✅ Good: Command object
@dataclass
class MarkSummaryAsReadCommand:
    summary_id: int
    user_id: int

async def execute(self, command: MarkSummaryAsReadCommand):
    pass
```

### Pattern 3: Domain Events

**Don't**: Direct coupling with side effects

```python
# ❌ Bad: Direct coupling
async def mark_as_read(self, summary_id: int):
    await self._repo.mark_as_read(summary_id)
    await self._notifier.send_notification(...)  # Direct coupling
```

**Do**: Emit domain events

```python
# ✅ Good: Domain events
async def mark_as_read(self, summary_id: int):
    await self._repo.mark_as_read(summary_id)

    # Emit event for loose coupling
    event = SummaryMarkedAsRead(
        occurred_at=datetime.utcnow(),
        summary_id=summary_id,
    )
    return event  # Caller can publish to event bus
```

### Pattern 4: Repository Pattern

**Don't**: Direct database access in use cases

```python
# ❌ Bad: Direct database access
async def execute(self, command):
    result = await self._db.raw_query("SELECT * FROM summaries...")
```

**Do**: Repository abstraction

```python
# ✅ Good: Repository pattern
async def execute(self, command):
    summary = await self._summary_repo.get_by_id(command.summary_id)
```

## Examples

### Example 1: Query Use Case

```python
# app/application/use_cases/get_unread_summaries.py

@dataclass
class GetUnreadSummariesCommand:
    user_id: int
    chat_id: int
    limit: int = 10

class GetUnreadSummariesUseCase:
    """Use case for retrieving unread summaries."""

    def __init__(self, summary_repo: SummaryRepository):
        self._repo = summary_repo

    async def execute(
        self,
        command: GetUnreadSummariesCommand
    ) -> list[Summary]:
        """Get unread summaries for a user."""
        # Simple query - just delegate to repository
        db_summaries = await self._repo.async_get_unread_summaries(
            uid=command.user_id,
            cid=command.chat_id,
            limit=command.limit,
        )

        # Convert to domain models
        return [
            self._repo.to_domain_model(db_summary)
            for db_summary in db_summaries
        ]
```

### Example 2: Complex Workflow Use Case

```python
# app/application/use_cases/summarize_url.py

@dataclass
class SummarizeUrlCommand:
    url: str
    user_id: int
    chat_id: int
    language: str | None = None

class SummarizeUrlUseCase:
    """Use case for complete URL summarization workflow."""

    def __init__(
        self,
        request_repo: RequestRepository,
        summary_repo: SummaryRepository,
        content_fetcher: IContentFetcher,
        llm_client: ILLMClient,
        summary_validator: SummaryValidator,
    ):
        self._request_repo = request_repo
        self._summary_repo = summary_repo
        self._content_fetcher = content_fetcher
        self._llm_client = llm_client
        self._validator = summary_validator

    async def execute(
        self,
        command: SummarizeUrlCommand
    ) -> tuple[Request, Summary]:
        """Execute the full summarization workflow."""
        # 1. Create request record
        request = Request(
            user_id=command.user_id,
            chat_id=command.chat_id,
            request_type=RequestType.URL,
            input_url=command.url,
        )
        # Persist and get ID
        request_data = self._request_repo.from_domain_model(request)
        request_id = await self._request_repo.create(**request_data)
        request.id = request_id

        try:
            # 2. Mark as crawling
            request.mark_as_crawling()
            await self._request_repo.update_status(
                request_id,
                request.status.value
            )

            # 3. Fetch content
            content = await self._content_fetcher.fetch(command.url)

            # 4. Mark as summarizing
            request.mark_as_summarizing()
            await self._request_repo.update_status(
                request_id,
                request.status.value
            )

            # 5. Generate summary via LLM
            llm_response = await self._llm_client.chat(
                messages=[...],  # Build messages
            )

            # 6. Create summary domain model
            summary = Summary(
                request_id=request_id,
                content=llm_response.data,
                language=command.language or 'en',
            )

            # 7. Validate summary
            self._validator.validate_summary(summary)

            # 8. Persist summary
            version = await self._summary_repo.async_upsert_summary(
                request_id=request_id,
                lang=summary.language,
                json_payload=summary.content,
            )

            # 9. Mark request as completed
            request.mark_as_completed()
            await self._request_repo.update_status(
                request_id,
                request.status.value
            )

            return request, summary

        except Exception as e:
            # Mark request as failed
            request.mark_as_error()
            await self._request_repo.update_status(
                request_id,
                request.status.value
            )
            raise
```

## Testing

### Testing Domain Layer

Domain layer has no dependencies, so tests are simple:

```python
# tests/domain/models/test_summary.py
import pytest
from app.domain.models.summary import Summary

def test_mark_as_read():
    """Test marking summary as read."""
    summary = Summary(
        request_id=1,
        content={'tldr': 'Test'},
        language='en',
        is_read=False,
    )

    summary.mark_as_read()

    assert summary.is_read is True

def test_mark_as_read_when_already_read_raises_error():
    """Test that marking read summary as read raises error."""
    summary = Summary(
        request_id=1,
        content={'tldr': 'Test'},
        language='en',
        is_read=True,
    )

    with pytest.raises(ValueError, match="already marked as read"):
        summary.mark_as_read()
```

### Testing Use Cases

Use cases can be tested with mock repositories:

```python
# tests/application/use_cases/test_mark_summary_as_read.py
import pytest
from app.application.use_cases.mark_summary_as_read import (
    MarkSummaryAsReadCommand,
    MarkSummaryAsReadUseCase,
)

class MockSummaryRepository:
    """Mock repository for testing."""

    def __init__(self):
        self.summaries = {}

    async def async_mark_summary_as_read(self, summary_id: int):
        if summary_id not in self.summaries:
            raise Exception("Not found")
        self.summaries[summary_id]['is_read'] = True

@pytest.mark.asyncio
async def test_mark_summary_as_read_success():
    """Test successfully marking summary as read."""
    # Arrange
    mock_repo = MockSummaryRepository()
    mock_repo.summaries[123] = {'id': 123, 'is_read': False}
    use_case = MarkSummaryAsReadUseCase(mock_repo)
    command = MarkSummaryAsReadCommand(summary_id=123, user_id=456)

    # Act
    event = await use_case.execute(command)

    # Assert
    assert event.summary_id == 123
    assert mock_repo.summaries[123]['is_read'] is True
```

## FAQs

### Q: Where do I put validation logic?

**A**: Depends on the type:

- **Domain validation** (business rules): Domain layer
  - Example: "Summary must have at least one key idea"
  - Location: `domain/services/summary_validator.py`

- **Application validation** (workflow rules): Application layer
  - Example: "User must be authenticated to create summary"
  - Location: Use case's `execute()` method

- **Input validation** (format checks): Presentation layer
  - Example: "URL must be valid format"
  - Location: Command handler

### Q: Should I create a use case for every operation?

**A**: Generally yes, but you can simplify for basic CRUD:

- **Simple queries**: Can go directly from handler to repository
- **Business workflows**: Always use a use case
- **Complex queries with business logic**: Use case
- **Simple updates with no validation**: Can skip use case

Rule of thumb: If it's just CRUD with no business logic, you can skip the use case.

### Q: How do I handle transactions?

**A**: Use cases define transaction boundaries:

```python
async def execute(self, command):
    async with self._db.transaction():  # Start transaction
        # All repository calls in this block are part of transaction
        await self._request_repo.create(...)
        await self._summary_repo.create(...)
        # Commits on success, rolls back on exception
```

### Q: What about existing code?

**A**: Incremental migration:

1. Keep existing code working
2. Add new features using new architecture
3. Gradually refactor old features
4. No need for big rewrite

Both old and new can coexist during transition.

### Q: How do I inject dependencies?

**A**: Create a DI container (future work) or manual wiring:

```python
# Manual wiring in bot initialization
database = Database(db_path)
summary_repo = SqliteSummaryRepositoryAdapter(database)
use_case = MarkSummaryAsReadUseCase(summary_repo)
handler = SummaryCommandHandler(use_case)
```

### Q: Where do domain events go?

**A**: Use cases return events, presentation layer publishes them:

```python
# Use case returns event
event = await use_case.execute(command)

# Handler publishes to event bus (future work)
await event_bus.publish(event)
```

## Quick Reference

| Task | Layer | Example |
|------|-------|---------|
| Business rule | Domain | "Summary must have content" |
| Entity behavior | Domain | `summary.mark_as_read()` |
| Workflow | Application | "Fetch, summarize, save" |
| Database query | Infrastructure | `SELECT * FROM summaries` |
| Format for user | Presentation | "✅ Summary created!" |
| External API call | Infrastructure | `await openrouter.chat(...)` |
| State validation | Domain | `can_mark_as_read()` |
| Orchestration | Application | Use case `execute()` |
| User input parsing | Presentation | Extract URL from message |

## Next Steps

1. Read `ARCHITECTURE_PROPOSAL.md` for detailed architecture
2. Read `PHASE_1_IMPLEMENTATION_SUMMARY.md` for what's implemented
3. Look at example use case: `app/application/use_cases/mark_summary_as_read.py`
4. Look at example domain model: `app/domain/models/summary.py`
5. Start creating use cases for your features!

## Resources

- **SOLID Improvements**: `docs/SOLID_IMPROVEMENTS.md`
- **Architecture Proposal**: `docs/ARCHITECTURE_PROPOSAL.md`
- **Phase 1 Summary**: `docs/PHASE_1_IMPLEMENTATION_SUMMARY.md`
- **Domain Models**: `app/domain/models/`
- **Use Cases**: `app/application/use_cases/`
