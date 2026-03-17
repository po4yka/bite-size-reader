"""Backward-compatibility shim for ProgressTracker.

The class has been renamed to TelegramProgressMessage and moved to
app.core.telegram_progress_message. Import from there in new code.
"""

from app.core.telegram_progress_message import TelegramProgressMessage as ProgressTracker

__all__ = ["ProgressTracker"]
