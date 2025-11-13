# SOLID Principles Improvements

This document describes the SOLID principle improvements made to the codebase and provides guidance on how to continue improving the architecture.

## Table of Contents

1. [Overview](#overview)
2. [Changes Made](#changes-made)
3. [Protocol Definitions](#protocol-definitions)
4. [Repository Pattern](#repository-pattern)
5. [Command Pattern](#command-pattern)
6. [Future Improvements](#future-improvements)
7. [Migration Guide](#migration-guide)

## Overview

This refactoring addresses several SOLID principle violations identified in the codebase:

- **Single Responsibility Principle (SRP)**: Split large "god objects" into focused components
- **Open/Closed Principle (OCP)**: Use patterns that allow extension without modification
- **Interface Segregation Principle (ISP)**: Define focused interfaces instead of monolithic ones
- **Dependency Inversion Principle (DIP)**: Depend on abstractions, not concrete implementations

## Changes Made

### 1. Protocol Definitions (`app/protocols.py`)

Created protocol interfaces that define contracts for major abstractions:

- `RequestRepository`: Request CRUD operations
- `SummaryRepository`: Summary CRUD operations
- `CrawlResultRepository`: Crawl result operations
- `UserInteractionRepository`: User interaction logging
- `LLMCallRepository`: LLM call logging
- `LLMClient`: LLM client interface
- `MessageFormatter`: Message formatting interface
- `FileValidator`: File validation interface
- `RateLimiter`: Rate limiting interface

**Benefits:**
- Clear contracts that document expected behavior
- Enables dependency injection and easier testing
- Loose coupling between components
- Type safety with static analysis tools

**Example usage:**
```python
from app.protocols import SummaryRepository

class MySummaryService:
    def __init__(self, summary_repo: SummaryRepository):
        # Accept any implementation that provides the SummaryRepository interface
        self._repo = summary_repo

    async def get_recent_summaries(self, uid: int) -> list:
        return await self._repo.async_get_unread_summaries(uid, cid=0, limit=10)
```

### 2. Repository Implementations (`app/repositories.py`)

Created repository implementations that wrap the existing `Database` class:

- `RequestRepositoryImpl`: Focused interface for request operations
- `SummaryRepositoryImpl`: Focused interface for summary operations
- `CrawlResultRepositoryImpl`: Focused interface for crawl results
- `UserInteractionRepositoryImpl`: Focused interface for user interactions
- `LLMCallRepositoryImpl`: Focused interface for LLM call logging

**Benefits:**
- **Interface Segregation**: Clients only depend on the methods they use
- **Single Responsibility**: Each repository has one clear purpose
- **Testability**: Easy to create test doubles for specific repository interfaces
- **Incremental migration**: Can wrap existing Database class while planning future splits

**Example usage:**
```python
from app.db.database import Database
from app.repositories import SummaryRepositoryImpl

# Create the database
db = Database(db_path="app.db")

# Wrap it in a focused repository
summary_repo = SummaryRepositoryImpl(db)

# Pass only the interface the component needs
service = MySummaryService(summary_repo)
```

### 3. Updated LLMResponseWorkflow

Updated `app/adapters/content/llm_response_workflow.py` to use protocols:

**Before:**
```python
def __init__(self, *, db: Database, ...):
    self.db = db
```

**After:**
```python
def __init__(
    self,
    *,
    db: SummaryRepository & RequestRepository & LLMCallRepository,
    ...
):
    self.db = db
```

**Benefits:**
- Documents exactly which database operations this class uses
- Enables passing different implementations for testing
- Clarifies dependencies and responsibilities
- Improves maintainability by making interfaces explicit

### 4. Command Pattern (`app/adapters/telegram/commands.py`)

Created a command pattern implementation for bot commands:

- `CommandContext`: Encapsulates command execution context
- `Command` protocol: Defines command interface
- `CommandRegistry`: Manages command registration and routing
- Helper functions for adapting existing handlers

**Benefits:**
- **Open/Closed Principle**: Add new commands without modifying routing logic
- **Single Responsibility**: Each command is its own class
- **Testability**: Commands can be tested in isolation
- **Flexibility**: Support for conditional commands and aliases

**Example usage:**
```python
from app.adapters.telegram.commands import CommandRegistry, CommandContext, create_command_adapter

# Create registry
registry = CommandRegistry()

# Register commands
async def handle_start(context: CommandContext):
    await context.message.reply("Welcome!")

registry.register_command("/start", handle_start)

# Or adapt existing handlers
registry.register_command(
    "/help",
    create_command_adapter(
        command_processor.handle_help_command,
        extract_args=lambda ctx: (
            ctx.message, ctx.uid, ctx.correlation_id,
            ctx.interaction_id, ctx.start_time
        )
    )
)

# Route messages
context = CommandContext(message, text, uid, correlation_id, interaction_id, start_time)
handled = await registry.route_message(context)
```

## Protocol Definitions

### Using Protocols for Dependency Injection

Protocols enable structural subtyping (duck typing with type safety):

```python
from typing import Protocol

class SummaryRepository(Protocol):
    async def async_get_summary_by_request(
        self, request_id: int
    ) -> dict[str, Any] | None:
        ...
```

Any class that implements these methods is compatible:

```python
# Both of these work:
db = Database(db_path="app.db")  # Implements all repository protocols
summary_repo = SummaryRepositoryImpl(db)  # Focused repository

# Both can be used where SummaryRepository is expected
def process_summary(repo: SummaryRepository):
    ...

process_summary(db)  # ✓ Works
process_summary(summary_repo)  # ✓ Works
```

### Benefits of Protocol-Based Design

1. **Testability**: Create simple test doubles without complex mocking frameworks
2. **Flexibility**: Swap implementations without changing client code
3. **Documentation**: Protocols document the expected interface
4. **Type Safety**: Static type checkers (mypy, pyright) can verify correctness

## Repository Pattern

### Current State

The `Database` class (1888 lines) currently handles:
- Connection management
- Schema migrations
- Request CRUD
- Summary CRUD
- Crawl result operations
- User interaction logging
- LLM call logging
- Topic search indexing
- Database verification
- JSON normalization
- Backup operations

This violates the **Single Responsibility Principle** - it has too many reasons to change.

### Incremental Migration Strategy

The repository implementations provide an incremental migration path:

**Phase 1: Wrapper Repositories (Current)**
- Create protocol definitions ✓
- Create repository implementations that wrap Database ✓
- Update clients to use protocols in type hints ✓

**Phase 2: Direct Implementation (Future)**
- Move implementation from Database into repository classes
- Keep Database as a thin facade for backward compatibility
- Gradually migrate all clients to use repositories directly

**Phase 3: Full Separation (Future)**
- Remove Database class entirely
- Use dependency injection container for wiring
- Each repository is fully independent

### Example: Creating a Test Double

With protocols, creating test doubles is trivial:

```python
class MockSummaryRepository:
    """Test double for SummaryRepository."""

    def __init__(self):
        self.summaries = {}

    async def async_get_summary_by_request(self, request_id: int):
        return self.summaries.get(request_id)

    async def async_upsert_summary(self, request_id, lang, json_payload, **kwargs):
        self.summaries[request_id] = {"lang": lang, "data": json_payload}
        return 1

# Use in tests
mock_repo = MockSummaryRepository()
workflow = LLMResponseWorkflow(db=mock_repo, ...)
```

## Command Pattern

### Problem: Open/Closed Principle Violation

The current `MessageRouter._route_message_content()` method has a long chain of if/elif statements:

```python
if text.startswith("/start"):
    await self.command_processor.handle_start_command(...)
    return

if text.startswith("/help"):
    await self.command_processor.handle_help_command(...)
    return

# ... 15+ more commands ...
```

**Problems:**
- Adding a new command requires modifying this method
- Cannot add commands from plugins or extensions
- Difficult to test individual command routing
- Violates Open/Closed Principle

### Solution: Command Registry

The new command system allows commands to be registered dynamically:

```python
registry = CommandRegistry()

# Register commands
registry.register_command("/start", start_handler)
registry.register_command(["/find", "/findonline"], find_handler)

# Register conditional handlers
registry.register_conditional(
    condition=lambda ctx: ctx.has_forward,
    handler=forward_handler
)

# Route messages
context = CommandContext(message, text, uid, ...)
handled = await registry.route_message(context)
```

**Benefits:**
- Add commands without modifying routing code
- Commands can be registered from different modules
- Easy to test command routing in isolation
- Supports aliases and conditional routing

### Migration Path

1. **Keep existing routing**: The current if/elif chain still works
2. **Add registry alongside**: Create CommandRegistry instance in MessageRouter
3. **Register commands**: Move commands to registry one at a time
4. **Fallback to registry**: At the end of if/elif chain, check registry
5. **Remove if/elif chain**: Once all commands are registered
6. **Use only registry**: Simplify routing to just registry.route_message()

## Future Improvements

### High Priority

1. **Split Database Class**
   - Move request operations into RequestRepositoryImpl
   - Move summary operations into SummaryRepositoryImpl
   - Extract topic search indexing into TopicSearchIndexManager
   - Extract migrations into DatabaseMigrator
   - Keep Database as thin facade for compatibility

2. **Apply Command Pattern**
   - Create MessageRouter.setup_commands() method
   - Register all commands with CommandRegistry
   - Replace if/elif chain with registry.route_message()
   - Extract command handlers from CommandProcessor into separate Command classes

3. **Add More Protocols**
   - Create protocols for remaining abstractions (FirecrawlClient, URLProcessor, etc.)
   - Update all constructor parameter types to use protocols
   - Document expected interfaces with docstrings

### Medium Priority

4. **Split MessageRouter**
   - Extract RateLimitGuard for rate limiting
   - Extract FileProcessor for document handling
   - Extract ProgressTracker for progress reporting
   - Keep MessageRouter as orchestrator only

5. **Split LLMSummarizer**
   - Extract MetadataExtractor for metadata handling
   - Extract InsightsGenerator for insights generation
   - Extract ResponseParser for parsing logic
   - Keep LLMSummarizer focused on summarization only

6. **Split TelegramBot**
   - Extract DatabaseBackupService for backup management
   - Extract ComponentWiring for dependency injection
   - Keep TelegramBot focused on bot orchestration only

### Low Priority

7. **Extract Strategy Patterns**
   - Error handling strategies
   - Message formatting strategies
   - File validation strategies

8. **Add Dependency Injection Container**
   - Use a DI container (e.g., dependency-injector, inject)
   - Define component wiring in configuration
   - Eliminate manual instantiation in __init__ methods

## Migration Guide

### For New Code

When writing new code, follow these patterns:

1. **Define protocols first**
   ```python
   from typing import Protocol

   class MyRepository(Protocol):
       async def get_data(self, id: int) -> dict | None:
           ...
   ```

2. **Accept protocols in constructors**
   ```python
   class MyService:
       def __init__(self, repo: MyRepository):
           self._repo = repo
   ```

3. **Register commands instead of adding if statements**
   ```python
   registry.register_command("/mycommand", my_handler)
   ```

### For Existing Code

When modifying existing code:

1. **Add protocol type hints to parameters**
   ```python
   # Before
   def __init__(self, db: Database):

   # After
   def __init__(self, db: SummaryRepository & RequestRepository):
   ```

2. **Extract focused interfaces**
   - If a class needs only summaries, pass SummaryRepository
   - If it needs only requests, pass RequestRepository
   - Don't pass entire Database if not needed

3. **Document dependencies**
   - Add docstring explaining which protocols are used
   - Clarify why each dependency is needed

### Testing

Create simple test doubles instead of complex mocks:

```python
class FakeSummaryRepository:
    def __init__(self):
        self.data = {}

    async def async_get_summary_by_request(self, request_id):
        return self.data.get(request_id)

    async def async_upsert_summary(self, request_id, **kwargs):
        self.data[request_id] = kwargs
        return 1

# Use in tests
def test_workflow():
    fake_repo = FakeSummaryRepository()
    workflow = LLMResponseWorkflow(db=fake_repo, ...)
    # ... test ...
```

## Conclusion

These changes provide a foundation for improving the codebase architecture:

- **Protocols** enable loose coupling and easier testing
- **Repositories** provide focused interfaces for data access
- **Command Pattern** makes routing extensible
- **Incremental migration** allows gradual improvement without breaking changes

The patterns established here can be applied to other areas of the codebase to continue improving maintainability, testability, and adherence to SOLID principles.

## References

- [SOLID Principles](https://en.wikipedia.org/wiki/SOLID)
- [Python Protocols (PEP 544)](https://peps.python.org/pep-0544/)
- [Repository Pattern](https://martinfowler.com/eaaCatalog/repository.html)
- [Command Pattern](https://refactoring.guru/design-patterns/command)
