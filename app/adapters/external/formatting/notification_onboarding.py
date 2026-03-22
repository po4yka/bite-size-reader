"""Welcome/help notification presenters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .notification_context import NotificationFormatterContext


class NotificationOnboardingPresenter:
    """Render simple onboarding/help messages."""

    def __init__(self, context: NotificationFormatterContext) -> None:
        self._context = context

    async def send_help(self, message: Any) -> None:
        help_text = (
            "Available Commands:\n"
            "  /start -- Welcome message and instructions\n"
            "  /help -- Show this help message\n"
            "  /summarize <URL> -- Summarize a URL\n"
            "  /summarize_all <URLs> -- Summarize multiple URLs from one message\n"
            "  /findweb <topic> -- Search the web (Firecrawl) for recent articles\n"
            "  /finddb <topic> -- Search your saved Bite-Size Reader library\n"
            "  /find <topic> -- Alias for /findweb\n"
            "  /cancel -- Cancel any pending URL or multi-link requests\n"
            "  /unread [topic] [limit] -- Show unread articles optionally filtered by topic\n"
            "  /read <ID> -- Mark article as read and view it\n"
            "  /dbinfo -- Show database overview\n"
            "  /dbverify -- Verify stored posts and required fields\n"
            "  /debug -- Toggle debug/reader notification mode\n\n"
            "Usage Tips:\n"
            "  Send URLs directly (commands are optional)\n"
            "  Forward channel posts to summarize them\n"
            "  Send /summarize and then a URL in the next message\n"
            "  Upload a .txt file with URLs (one per line) for batch processing\n"
            "  Multiple links in one message are supported\n"
            "  Use /unread [topic] [limit] to see saved articles by topic\n\n"
            "Features:\n"
            "  Structured JSON output with schema validation\n"
            "  Intelligent model fallbacks for better reliability\n"
            "  Automatic content optimization based on model capabilities\n"
            "  Silent batch processing for uploaded files\n"
            "  Progress tracking for multiple URLs"
        )
        await self._context.response_sender.safe_reply(message, help_text)

    async def send_welcome(self, message: Any) -> None:
        welcome = (
            "Welcome to Bite-Size Reader!\n\n"
            "What I do:\n"
            "- Summarize articles from URLs using Firecrawl + OpenRouter.\n"
            "- Summarize forwarded channel posts.\n"
            "- Generate structured JSON summaries with reliable results.\n\n"
            "How to use:\n"
            "- Send a URL directly, or use /summarize <URL>.\n"
            "- You can also send /summarize and then the URL in the next message.\n"
            "- For forwarded posts, use /summarize_forward and then forward a channel post.\n"
            '- Multiple links in one message are supported: I will ask "Process N links?" or use /summarize_all to process immediately.\n'
            "- /dbinfo shares a quick snapshot of the internal database so you can monitor storage.\n\n"
            "Notes:\n"
            "- I reply with a strict JSON object using advanced schema validation.\n"
            "- Intelligent model selection and fallbacks ensure high success rates.\n"
            "- Errors include an Error ID you can reference in logs."
        )
        await self._context.response_sender.safe_reply(message, welcome)
