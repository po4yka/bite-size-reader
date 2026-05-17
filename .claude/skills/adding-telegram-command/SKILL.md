---
name: adding-telegram-command
description: Add a new Telegram bot command to Ratatoskr via the command registry pattern. Trigger keywords -- new command, bot command, telegram handler, CommandRegistry, command_handlers, register_command, slash command.
version: 1.0.0
allowed-tools: Bash, Read, Write, Edit, Grep
---

# Adding a Telegram Command

Add a new slash command (`/foo`) to the Ratatoskr bot via the existing registry pattern.

## The Registry Pattern

Commands are NOT dispatched by `if text.startswith("/foo")` branches in the router. Instead:

1. Each command is a handler class in `app/adapters/telegram/command_handlers/`
2. The handler is registered via `CommandRegistry.register_command(...)` in `app/adapters/telegram/commands.py`
3. `MessageRouter` looks up the registry and delegates -- it does not know about specific commands

Adding a command means: create the handler, register it, write tests. Done.

## Steps

### 1. Create the handler

`app/adapters/telegram/command_handlers/foo_command.py`:

```python
from app.adapters.telegram.command_handlers.base import BaseCommandHandler
from app.adapters.telegram.response_formatter import ResponseFormatter

class FooCommandHandler(BaseCommandHandler):
    name = "foo"
    description = "One-line user-facing description"

    async def handle(self, message, args: list[str]) -> None:
        # args is the tokenized argument list after the command word
        formatter: ResponseFormatter = self.container.response_formatter
        await formatter.reply(message, "Foo did the thing.")
```

Match the constructor signature and lifecycle of an existing simple handler (e.g. `app/adapters/telegram/command_handlers/help_command.py`) -- they're injected via the DI container.

### 2. Register it

`app/adapters/telegram/commands.py`:

```python
from app.adapters.telegram.command_handlers.foo_command import FooCommandHandler

def build_registry(container) -> CommandRegistry:
    registry = CommandRegistry()
    # ... existing
    registry.register_command(FooCommandHandler(container))
    return registry
```

### 3. Reply via `ResponseFormatter`

Always use `ResponseFormatter` (not raw `message.reply_text(...)`). It centralizes logging, correlation-ID attachment, and error envelope formatting.

### 4. Write tests

`tests/adapters/telegram/test_foo_command.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.adapters.telegram.command_handlers.foo_command import FooCommandHandler

@pytest.mark.asyncio
async def test_foo_replies():
    container = MagicMock()
    container.response_formatter.reply = AsyncMock()

    handler = FooCommandHandler(container)
    await handler.handle(message=MagicMock(), args=[])

    container.response_formatter.reply.assert_awaited_once()
```

For commands that hit the DB, use `tests/db_helpers.py` instead of writing fresh fixtures (per CLAUDE.md rule).

### 5. (Optional) BotFather command list

If the command should appear in Telegram's command menu, update the registered command list with BotFather -- that's a one-time manual step, not code.

## Access Control

If the command should be owner-only (default), the existing `AccessController` (`app/adapters/telegram/access_controller.py`) already gates the message router on `ALLOWED_USER_IDS`. New commands inherit the gate automatically. For commands that should be PUBLIC (rare), check how the digest commands handle this -- they use an explicit bypass.

## Existing Commands (Reference)

Look at these as templates:

| File | Pattern |
| ---- | ------- |
| `help_command.py` | Simplest -- static reply |
| `init_session_command.py` | Multi-step interaction (OTP/2FA flow) |
| `digest_command.py` | DB-backed query + formatted reply |
| `subscribe_command.py` | Mutates DB + confirms |
| `channels_command.py` | Lists DB rows |

## Key Files

- **Handlers**: `app/adapters/telegram/command_handlers/`
- **Registry**: `app/adapters/telegram/commands.py`
- **Router**: `app/adapters/telegram/message_router.py`
- **Access control**: `app/adapters/telegram/access_controller.py`
- **Reply helper**: `app/adapters/telegram/response_formatter.py`
- **Telegram message model**: `app/models/telegram/telegram_message.py`
- **DI container**: `app/di/`

## Important Notes

- `MessageRouter` is the only caller of the registry -- do not invoke handlers directly from elsewhere.
- The handler's `name` field is the slash command word (no leading `/`).
- Errors should include `Error ID: <correlation_id>` in user-visible messages (CLAUDE.md rule).
- Persist any side effects in the appropriate table (`requests`, `audit_logs`, etc.) -- the observability discipline matters.
- For long-running operations, use the in-process `StreamHub` (`app/adapters/content/streaming/`) so the user gets progress updates instead of a frozen reply.
