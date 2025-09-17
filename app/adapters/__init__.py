"""Adapters for external systems: Firecrawl, OpenRouter, Telegram client.

This package re-exports convenience module aliases used by tests and
downstream code (e.g., ``app.adapters.telegram_bot``) by importing the
corresponding modules from the structured subpackages.
"""

# Re-export telegram bot module at package level for compatibility with tests
# that import ``app.adapters.telegram_bot``.
from .telegram import telegram_bot as telegram_bot  # noqa: F401
