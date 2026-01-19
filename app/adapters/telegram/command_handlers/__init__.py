"""Command handlers for Telegram bot.

This package contains decomposed command handlers that were extracted from
the monolithic CommandProcessor class. Each handler module is responsible
for a specific group of related commands.

Modules:
- execution_context: CommandExecutionContext dataclass for handler parameters
- decorators: Reusable decorators for logging, auditing, and interaction tracking
- error_handler: Context manager for standardized error handling
- utils: Shared utility functions

Handler Modules:
- onboarding_handler: /start, /help commands
- admin_handler: /dbinfo, /dbverify commands
- url_commands_handler: /summarize, /summarize_all, /cancel commands
- content_handler: /unread, /read commands
- search_handler: /find*, /search commands
- karakeep_handler: /sync_karakeep command
"""

from app.adapters.telegram.command_handlers.admin_handler import AdminHandlerImpl
from app.adapters.telegram.command_handlers.content_handler import ContentHandlerImpl
from app.adapters.telegram.command_handlers.decorators import audit_command, track_interaction
from app.adapters.telegram.command_handlers.error_handler import command_error_handler
from app.adapters.telegram.command_handlers.execution_context import CommandExecutionContext
from app.adapters.telegram.command_handlers.karakeep_handler import KarakeepHandlerImpl
from app.adapters.telegram.command_handlers.onboarding_handler import OnboardingHandlerImpl
from app.adapters.telegram.command_handlers.search_handler import SearchHandlerImpl
from app.adapters.telegram.command_handlers.url_commands_handler import URLCommandsHandlerImpl
from app.adapters.telegram.command_handlers.utils import maybe_load_json

__all__ = [
    "AdminHandlerImpl",
    "CommandExecutionContext",
    "ContentHandlerImpl",
    "KarakeepHandlerImpl",
    "OnboardingHandlerImpl",
    "SearchHandlerImpl",
    "URLCommandsHandlerImpl",
    "audit_command",
    "command_error_handler",
    "maybe_load_json",
    "track_interaction",
]
