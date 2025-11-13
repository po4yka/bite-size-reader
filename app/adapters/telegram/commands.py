"""Command Pattern implementation for Telegram bot commands.

This module provides a registry-based command system that follows the Open/Closed
Principle, allowing new commands to be added without modifying routing logic.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class CommandContext:
    """Context object containing all information needed to execute a command."""

    def __init__(
        self,
        message: Any,
        text: str,
        uid: int,
        correlation_id: str,
        interaction_id: int,
        start_time: float,
        has_forward: bool = False,
    ) -> None:
        self.message = message
        self.text = text
        self.uid = uid
        self.correlation_id = correlation_id
        self.interaction_id = interaction_id
        self.start_time = start_time
        self.has_forward = has_forward


class Command(Protocol):
    """Protocol for command handlers.

    All command implementations must provide an execute method that accepts
    a CommandContext and returns a boolean indicating whether routing should continue.
    """

    async def execute(self, context: CommandContext) -> bool:
        """Execute the command.

        Args:
            context: The command execution context.

        Returns:
            True if routing should continue to check other handlers,
            False if this command handled the message and routing should stop.

        """
        ...


@dataclass
class SimpleCommand:
    """Simple command implementation that wraps a handler function."""

    handler: Callable[[CommandContext], Awaitable[None]]

    async def execute(self, context: CommandContext) -> bool:
        """Execute the wrapped handler."""
        await self.handler(context)
        return False  # Stop routing after handling


@dataclass
class ConditionalCommand:
    """Command that checks a condition before executing."""

    condition: Callable[[CommandContext], bool | Awaitable[bool]]
    handler: Callable[[CommandContext], Awaitable[None]]

    async def execute(self, context: CommandContext) -> bool:
        """Execute handler only if condition is met."""
        # Handle both sync and async conditions
        if callable(self.condition):
            result = self.condition(context)
            if isinstance(result, Awaitable):
                should_execute = await result
            else:
                should_execute = result
        else:
            should_execute = self.condition

        if should_execute:
            await self.handler(context)
            return False  # Stop routing
        return True  # Continue to next handler


class CommandRegistry:
    """Registry for managing command handlers.

    Commands are registered with prefixes and checked in registration order.
    This allows for flexible command matching including:
    - Exact prefix matches (/start, /help)
    - Multiple aliases for the same command
    - Conditional routing based on message state
    """

    def __init__(self) -> None:
        self._commands: list[tuple[list[str] | None, Command]] = []

    def register_command(
        self,
        prefixes: str | list[str] | None,
        handler: Command | Callable[[CommandContext], Awaitable[None]],
    ) -> None:
        """Register a command handler.

        Args:
            prefixes: Command prefix(es) to match (e.g., "/start" or ["/find", "/findonline"]).
                     If None, this is a fallback handler that matches any message.
            handler: Command handler (Command protocol or async callable).

        """
        # Normalize prefixes to list
        if prefixes is None:
            prefix_list = None
        elif isinstance(prefixes, str):
            prefix_list = [prefixes]
        else:
            prefix_list = list(prefixes)

        # Wrap plain functions in SimpleCommand
        if not isinstance(handler, (SimpleCommand, ConditionalCommand)):
            if callable(handler):
                handler = SimpleCommand(handler)

        self._commands.append((prefix_list, handler))

    def register_conditional(
        self,
        condition: Callable[[CommandContext], bool | Awaitable[bool]],
        handler: Callable[[CommandContext], Awaitable[None]],
    ) -> None:
        """Register a conditional handler that only executes if condition is met.

        Args:
            condition: Function that returns True if handler should execute.
            handler: Async handler function to execute.

        """
        self._commands.append((None, ConditionalCommand(condition, handler)))

    async def route_message(self, context: CommandContext) -> bool:
        """Route a message through registered command handlers.

        Args:
            context: The command context containing message information.

        Returns:
            True if a command handled the message, False otherwise.

        """
        text = context.text

        for prefixes, command in self._commands:
            # Check if this command matches the message
            should_execute = False

            if prefixes is None:
                # No prefix means this is a conditional or fallback handler
                # The command itself will decide if it should execute
                should_execute = True
            else:
                # Check if text starts with any of the registered prefixes
                for prefix in prefixes:
                    if text.startswith(prefix):
                        should_execute = True
                        break

            if should_execute:
                try:
                    # Execute command and check if routing should continue
                    should_continue = await command.execute(context)
                    if not should_continue:
                        # Command handled the message, stop routing
                        return True
                except Exception as exc:
                    logger.exception(
                        "command_execution_error",
                        extra={
                            "error": str(exc),
                            "cid": context.correlation_id,
                            "prefixes": prefixes,
                        },
                    )
                    # Continue to next handler on error
                    continue

        # No command handled the message
        return False

    def clear(self) -> None:
        """Clear all registered commands."""
        self._commands.clear()


def create_command_adapter(
    handler: Callable[..., Awaitable[None]],
    *,
    extract_args: Callable[[CommandContext], tuple[Any, ...]] | None = None,
    extract_kwargs: Callable[[CommandContext], dict[str, Any]] | None = None,
) -> Callable[[CommandContext], Awaitable[None]]:
    """Create an adapter that converts CommandContext to handler parameters.

    This helper function allows existing handler methods to be used with the
    command system without modification.

    Args:
        handler: The handler function to wrap.
        extract_args: Optional function to extract positional args from context.
        extract_kwargs: Optional function to extract keyword args from context.

    Returns:
        An async function that accepts CommandContext.

    Example:
        ```python
        async def handle_start(message, uid, correlation_id, interaction_id, start_time):
            # ... existing handler code ...

        # Create adapter
        adapted_handler = create_command_adapter(
            handle_start,
            extract_args=lambda ctx: (ctx.message, ctx.uid, ctx.correlation_id,
                                     ctx.interaction_id, ctx.start_time)
        )

        # Register with command registry
        registry.register_command("/start", adapted_handler)
        ```

    """

    async def adapter(context: CommandContext) -> None:
        args = extract_args(context) if extract_args else ()
        kwargs = extract_kwargs(context) if extract_kwargs else {}
        await handler(*args, **kwargs)

    return adapter
