# Hexagonal Architecture Quick Start

## Architecture Overview

```
Presentation (Telegram) → Application (Use Cases) → Domain (Business Logic) → Infrastructure (DB/APIs)
```

**Key Rule**: Dependencies point inward. Domain has no dependencies on outer layers.

## Layers

### Domain (`app/domain/`)
- **Purpose**: Core business logic independent of technology
- **Contains**: Business rules, entity behavior, domain events, exceptions
- **Example**: "A summary can only be marked as read if it has content"

### Application (`app/application/use_cases/`)
- **Purpose**: Orchestrate domain objects to fulfill workflows
- **Contains**: Use case implementations, transaction boundaries
- **Example**: "To summarize a URL, fetch content → generate summary → save it"

### Infrastructure (`app/infrastructure/`)
- **Purpose**: Implementation of external concerns
- **Contains**: Database repositories, API clients, messaging
- **Example**: SQLite repository that implements the repository protocol

### Presentation (`app/adapters/telegram/`, `app/presentation/`)
- **Purpose**: Handle user interaction
- **Contains**: Command handlers, message formatters
- **Example**: Parse `/unread` command and call use case

## Creating a New Feature

### 1. Define Domain Model (if needed)

```python
# app/domain/models/summary.py
class Summary:
    def mark_as_read(self) -> SummaryMarkedAsRead:
        if not self.content:
            raise InvalidStateTransitionError("Cannot mark empty summary as read")
        self.is_read = True
        return SummaryMarkedAsRead(summary_id=self.id)
```

### 2. Create Use Case

```python
# app/application/use_cases/mark_summary_as_read.py
class MarkSummaryAsReadUseCase:
    def __init__(self, summary_repository: SummaryRepository):
        self._summary_repo = summary_repository

    async def execute(self, command: MarkSummaryAsReadCommand) -> SummaryMarkedAsRead:
        summary = await self._summary_repo.get_by_id(command.summary_id)
        event = summary.mark_as_read()  # Domain logic
        await self._summary_repo.save(summary)
        return event
```

### 3. Wire in DI Container

```python
# app/di/container.py
def mark_summary_as_read_use_case(self) -> MarkSummaryAsReadUseCase:
    return MarkSummaryAsReadUseCase(
        summary_repository=self.summary_repository()
    )
```

### 4. Use in Handler

```python
# app/adapters/telegram/command_processor.py
use_case = self._container.mark_summary_as_read_use_case()
event = await use_case.execute(MarkSummaryAsReadCommand(summary_id=123))
await self._event_bus.publish(event)
```

## Common Patterns

### Command Pattern (Write Operations)
```python
@dataclass
class MarkSummaryAsReadCommand:
    summary_id: int
    user_id: int
```

### Query Pattern (Read Operations)
```python
@dataclass
class GetUnreadSummariesQuery:
    user_id: int
    limit: int = 10
```

### Domain Events
```python
@dataclass
class SummaryMarkedAsRead(DomainEvent):
    summary_id: int
    occurred_at: datetime
```

## Dependency Injection

The `Container` (`app/di/container.py`) wires all dependencies:

```python
# Initialize
container = Container(database=db, topic_search_service=search)

# Get use cases
use_case = container.mark_summary_as_read_use_case()
```

## Event Bus

Domain events enable loose coupling:

```python
# Publish event
await event_bus.publish(SummaryMarkedAsRead(summary_id=123))

# Subscribe handlers
event_bus.subscribe(SummaryMarkedAsRead, log_read_event)
event_bus.subscribe(SummaryMarkedAsRead, update_search_index)
```

## Testing

### Unit Test Use Case
```python
async def test_mark_summary_as_read():
    # Arrange
    mock_repo = Mock(SummaryRepository)
    use_case = MarkSummaryAsReadUseCase(summary_repository=mock_repo)

    # Act
    event = await use_case.execute(MarkSummaryAsReadCommand(summary_id=1))

    # Assert
    assert event.summary_id == 1
    mock_repo.save.assert_called_once()
```

### Integration Test
```python
async def test_mark_summary_integration():
    container = Container(database=test_db)
    use_case = container.mark_summary_as_read_use_case()

    event = await use_case.execute(MarkSummaryAsReadCommand(summary_id=1))

    # Verify in database
    summary = await test_db.get_summary_by_id(1)
    assert summary.is_read is True
```

## Files Structure

```
app/
├── domain/              # Business logic
│   ├── models/         # Entity classes
│   ├── events/         # Domain events
│   ├── exceptions/     # Domain exceptions
│   └── services/       # Domain services
├── application/         # Use cases
│   └── use_cases/      # Use case implementations
├── infrastructure/      # External implementations
│   ├── persistence/    # Repository implementations
│   └── messaging/      # Event bus
├── adapters/           # External interfaces
│   └── telegram/       # Telegram bot adapter
├── presentation/       # Handler examples
└── di/                 # Dependency injection
    └── container.py    # DI container
```

## FAQs

**Q: When should I create a new use case?**
A: When you have a distinct user workflow (e.g., mark as read, get unread summaries).

**Q: Where do I put validation?**
A: Business rules → Domain; Input validation → Application/Presentation.

**Q: How do I access the database?**
A: Use cases depend on repository protocols, implemented by Infrastructure layer.

**Q: What about the existing code?**
A: Both architectures coexist. The Container wraps the existing Database, so old and new code work together.

---

For examples, see `app/presentation/example_handler.py`.
