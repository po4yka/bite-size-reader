# Migration Guide: Moving to Hexagonal Architecture

This guide shows you how to migrate existing code to use the new hexagonal architecture. It provides step-by-step instructions with real examples from the codebase.

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Initialize the Container](#step-1-initialize-the-container)
3. [Step 2: Wire Event Handlers](#step-2-wire-event-handlers)
4. [Step 3: Migrate Command Handlers](#step-3-migrate-command-handlers)
5. [Step 4: Use Domain Events](#step-4-use-domain-events)
6. [Step 5: Add Custom Event Handlers](#step-5-add-custom-event-handlers)
7. [Common Patterns](#common-patterns)
8. [Troubleshooting](#troubleshooting)

## Overview

The migration is **gradual and backward-compatible**. You can migrate one command at a time while keeping existing code working.

**Key principle**: Old and new code coexist peacefully because they both use the same underlying `Database` instance.

## Step 1: Initialize the Container

### Where: Bot Initialization

Add the container initialization in `TelegramBot.__post_init__()`:

```python
# app/adapters/telegram/telegram_bot.py

from app.di.container import Container

class TelegramBot:
    def __post_init__(self) -> None:
        # ... existing initialization code ...

        # NEW: Create DI container
        self._container = Container(
            database=self.db,
            topic_search_service=self.topic_search_service,
            content_fetcher=self.firecrawl,  # If you have it
            llm_client=self.openrouter,      # If you have it
            analytics_service=None,           # Optional
        )

        # NEW: Wire event handlers
        self._container.wire_event_handlers_auto()

        logger.info("Container initialized and event handlers wired")
```

**That's it!** The container is now available to all handlers.

## Step 2: Wire Event Handlers

Event handlers are automatically wired by calling `wire_event_handlers_auto()` in Step 1.

This enables:
- ✅ **Search index updates** when summaries are created
- ✅ **Audit logging** for all important events
- ✅ **Analytics tracking** (if analytics service configured)

### Verify It Works

Events are now automatically handled. When a summary is created, you'll see logs like:

```
INFO - updating_search_index_for_new_summary - summary_id=123, request_id=456
DEBUG - search_index_updated - request_id=456, summary_id=123
```

## Step 3: Migrate Command Handlers

Let's migrate existing command handlers one at a time.

### Example 1: Migrate `/unread` Command

**Before** (direct database access):

```python
# app/adapters/telegram/command_processor.py

async def handle_unread_command(self, message, text, uid, cid, ...):
    # Parse limit from text
    limit = self._parse_limit_from_text(text, default=10)

    # Direct database call
    unread_summaries = await self.db.async_get_unread_summaries(uid, cid, limit)

    if not unread_summaries:
        await self.response_formatter.safe_reply(message, "No unread summaries")
        return

    # Format and send
    for idx, summary in enumerate(unread_summaries, 1):
        formatted = format_summary(summary)
        await send_message(formatted)
```

**After** (using container and use case):

```python
# app/adapters/telegram/command_processor.py

from app.application.use_cases.get_unread_summaries import (
    GetUnreadSummariesQuery,
)

class CommandProcessor:
    def __init__(
        self,
        container: Container,  # NEW: Accept container
        # ... other dependencies ...
    ):
        self._container = container
        # ... existing init ...

    async def handle_unread_command(self, message, text, uid, cid, ...):
        # Parse limit from text
        limit = self._parse_limit_from_text(text, default=10)

        # NEW: Create query
        query = GetUnreadSummariesQuery(
            user_id=uid,
            chat_id=cid,
            limit=limit,
        )

        # NEW: Get use case from container
        use_case = self._container.get_unread_summaries_use_case()

        # NEW: Execute use case
        summaries = await use_case.execute(query)

        if not summaries:
            await self.response_formatter.safe_reply(message, "No unread summaries")
            return

        # Format and send (same as before)
        for idx, summary in enumerate(summaries, 1):
            # summary is now a domain model with methods
            formatted = f"{idx}. {summary.get_tldr()[:100]}..."
            await send_message(formatted)
```

**Benefits**:
- Clearer intent with `GetUnreadSummariesQuery`
- Domain models with behavior (`summary.get_tldr()`)
- Easier to test (mock the use case)
- Centralized business logic

### Example 2: Migrate `/read` Command

**Before** (direct database access):

```python
async def handle_read_command(self, message, text, uid, ...):
    # Parse summary ID
    summary_id = extract_id_from_text(text)

    # Direct database call
    await self.db.async_mark_summary_as_read(summary_id)

    await self.response_formatter.safe_reply(message, "✅ Marked as read")
```

**After** (using use case with events):

```python
from app.application.use_cases.mark_summary_as_read import (
    MarkSummaryAsReadCommand,
)

async def handle_read_command(self, message, text, uid, ...):
    # Parse summary ID
    summary_id = extract_id_from_text(text)

    # NEW: Create command
    command = MarkSummaryAsReadCommand(
        summary_id=summary_id,
        user_id=uid,
    )

    # NEW: Get use case from container
    use_case = self._container.mark_summary_as_read_use_case()

    try:
        # NEW: Execute use case (returns event)
        event = await use_case.execute(command)

        # NEW: Publish event (for side effects)
        event_bus = self._container.event_bus()
        await event_bus.publish(event)

        await self.response_formatter.safe_reply(message, "✅ Marked as read")

    except InvalidStateTransitionError as e:
        # Domain exception - already read
        await self.response_formatter.safe_reply(message, f"❌ {e.message}")
```

**Benefits**:
- Domain events trigger side effects automatically
- Better error handling with domain exceptions
- Clear separation between command execution and side effects
- Analytics and audit logs updated automatically via events

### Example 3: Migrate `/find` Command

**Before** (direct service call):

```python
async def handle_find_online_command(self, message, text, uid, ...):
    # Parse topic
    topic = extract_topic_from_text(text)

    # Direct service call
    articles = await self.topic_search_service.find_articles(topic)

    # Format and send
    if not articles:
        await send_message("No articles found")
        return

    for article in articles:
        await send_message(f"{article.title}: {article.url}")
```

**After** (using use case):

```python
from app.application.use_cases.search_topics import SearchTopicsQuery

async def handle_find_online_command(self, message, text, uid, cid, correlation_id, ...):
    # Parse topic
    topic = extract_topic_from_text(text)

    # NEW: Create query
    query = SearchTopicsQuery(
        topic=topic,
        user_id=uid,
        max_results=5,
        correlation_id=correlation_id,
    )

    # NEW: Get use case from container
    use_case = self._container.search_topics_use_case()

    if use_case is None:
        await send_message("❌ Search not configured")
        return

    try:
        # NEW: Execute use case
        articles = await use_case.execute(query)

        # Format and send (with domain objects)
        if not articles:
            await send_message("No articles found")
            return

        for article in articles:
            await send_message(f"{article.title}: {article.url}")

    except ValueError as e:
        # Validation error
        await send_message(f"❌ Invalid search: {e}")
```

**Benefits**:
- Validation happens in the query object
- Graceful handling of missing dependencies
- Consistent error handling pattern
- Clear separation of concerns

## Step 4: Use Domain Events

Domain events enable loose coupling. Here's how to use them:

### Publishing Events

Events are automatically generated by use cases:

```python
# In your handler
use_case = self._container.mark_summary_as_read_use_case()
event = await use_case.execute(command)  # Returns SummaryMarkedAsRead event

# Publish to event bus
event_bus = self._container.event_bus()
await event_bus.publish(event)  # All subscribed handlers are called
```

### What Happens When You Publish?

When you publish `SummaryMarkedAsRead`, these handlers run automatically:
1. **SearchIndexEventHandler** - Updates FTS index
2. **AnalyticsEventHandler** - Tracks analytics
3. **AuditLogEventHandler** - Logs to audit log

All of this happens without your handler knowing about it!

## Step 5: Add Custom Event Handlers

Want to add your own side effects? Subscribe to events:

### Example: Send Notification When Summary Created

```python
# In your bot initialization, after container is created

from app.domain.events.summary_events import SummaryCreated

async def send_notification_on_summary_created(event: SummaryCreated):
    """Send notification when summary is created."""
    # Get summary details
    logger.info(f"New summary created: {event.summary_id}")

    # Send notification (implement your logic)
    await notification_service.send(
        f"Summary {event.summary_id} is ready!",
        user_id=...,  # Get from event or database
    )

# Subscribe to event
event_bus = self._container.event_bus()
event_bus.subscribe(SummaryCreated, send_notification_on_summary_created)
```

### Example: Update Cache When Summary Marked Read

```python
from app.domain.events.summary_events import SummaryMarkedAsRead

async def update_cache_on_read(event: SummaryMarkedAsRead):
    """Update cache when summary is marked as read."""
    # Invalidate cache for this summary
    cache_key = f"summary:{event.summary_id}"
    await redis_client.delete(cache_key)

    # Update user's unread count cache
    user_cache_key = f"user:unread_count:..."
    await redis_client.decr(user_cache_key)

event_bus.subscribe(SummaryMarkedAsRead, update_cache_on_read)
```

## Common Patterns

### Pattern 1: Pass Container to Handlers

Update your handler constructors to accept the container:

```python
# OLD
class CommandProcessor:
    def __init__(self, db: Database, ...):
        self.db = db

# NEW
class CommandProcessor:
    def __init__(
        self,
        container: Container,  # Accept container
        db: Database,          # Keep for backward compatibility
        ...
    ):
        self._container = container
        self.db = db  # Old code can still use this
```

### Pattern 2: Gradual Migration

You don't have to migrate everything at once:

```python
async def handle_commands(self, message, text, uid, ...):
    # New command using use case
    if text.startswith("/unread"):
        query = GetUnreadSummariesQuery(uid, cid, limit=10)
        use_case = self._container.get_unread_summaries_use_case()
        summaries = await use_case.execute(query)
        # ... handle ...
        return

    # Old command still using direct database access
    if text.startswith("/dbinfo"):
        stats = await self.db.get_database_overview()
        # ... handle ...
        return
```

Both work fine! Migrate when ready.

### Pattern 3: Error Handling

Handle domain exceptions gracefully:

```python
from app.domain.exceptions.domain_exceptions import (
    InvalidStateTransitionError,
    ValidationError,
    ResourceNotFoundError,
)

try:
    event = await use_case.execute(command)
    await event_bus.publish(event)
    await send_success_message()

except ValidationError as e:
    # Domain validation failed
    await send_error_message(f"❌ Invalid: {e.message}")
    logger.warning("validation_error", extra=e.details)

except InvalidStateTransitionError as e:
    # Business rule violation
    await send_error_message(f"❌ {e.message}")
    logger.info("state_transition_error", extra=e.details)

except ResourceNotFoundError as e:
    # Entity not found
    await send_error_message("❌ Not found")
    logger.error("resource_not_found", extra=e.details)

except Exception as e:
    # Unexpected error
    await send_error_message("❌ An error occurred")
    logger.exception("unexpected_error")
```

## Troubleshooting

### Issue: Container not initialized

**Error**: `AttributeError: 'TelegramBot' object has no attribute '_container'`

**Solution**: Make sure you initialized the container in `__post_init__()`:

```python
self._container = Container(database=self.db, ...)
```

### Issue: Use case returns None

**Error**: `AttributeError: 'NoneType' object has no attribute 'execute'`

**Cause**: Use case requires dependencies that weren't provided.

**Solution**: Check if use case is None before using:

```python
use_case = self._container.search_topics_use_case()
if use_case is None:
    await send_error("Feature not configured")
    return

result = await use_case.execute(query)
```

### Issue: Events not being handled

**Symptom**: Published events but handlers not called.

**Solution**: Make sure you wired event handlers:

```python
# In bot initialization
self._container.wire_event_handlers_auto()
```

Check logs for confirmation:

```
INFO - event_handlers_wired - summary_created_handlers=2, ...
```

### Issue: Old code breaks after migration

**This shouldn't happen!** Old code using `self.db` directly should still work.

If it does break:
1. Make sure `self.db` is still passed to handlers
2. Check that container wraps the same `Database` instance
3. Verify no accidental changes to `Database` class

## Migration Checklist

Use this checklist to track your migration progress:

- [ ] **Phase 1: Setup**
  - [ ] Initialize Container in bot
  - [ ] Wire event handlers
  - [ ] Verify events are logged

- [ ] **Phase 2: Simple Commands**
  - [ ] Migrate `/unread` to GetUnreadSummariesUseCase
  - [ ] Migrate `/read` to MarkSummaryAsReadUseCase
  - [ ] Test both commands work correctly

- [ ] **Phase 3: Complex Commands**
  - [ ] Migrate `/find` to SearchTopicsUseCase
  - [ ] Migrate other search commands
  - [ ] Test all search functionality

- [ ] **Phase 4: Custom Events**
  - [ ] Add notification handler
  - [ ] Add cache invalidation handler
  - [ ] Test side effects work

- [ ] **Phase 5: Cleanup**
  - [ ] Remove unused direct database calls
  - [ ] Update tests to use new architecture
  - [ ] Document new patterns in code

## Next Steps

After completing this migration:

1. **Add tests** - Use the new architecture to add unit tests
2. **Create more use cases** - Extract remaining business logic
3. **Split large classes** - Break down god objects
4. **Add domain services** - Extract complex business logic
5. **Improve error handling** - Use domain exceptions consistently

## Questions?

- Read `HEXAGONAL_ARCHITECTURE_QUICKSTART.md` for patterns
- Check `PHASE_1_IMPLEMENTATION_SUMMARY.md` for architecture details
- Check `PHASE_2_IMPLEMENTATION_SUMMARY.md` for event bus usage
- Look at `app/presentation/example_handler.py` for complete examples

## Summary

**Migration is gradual:**
1. Initialize container ✓
2. Wire event handlers ✓
3. Migrate one command at a time ✓
4. Old and new code coexist ✓
5. Add custom event handlers as needed ✓

**Benefits:**
- Better code organization
- Easier testing
- Loose coupling via events
- Clear separation of concerns
- Gradual, safe migration

Good luck with your migration! 🚀
