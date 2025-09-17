# ruff: noqa: E501
from __future__ import annotations

import io
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ResponseFormatter:
    """Handles message formatting and replies to Telegram users."""

    async def send_help(self, message: Any) -> None:
        """Send help message to user."""
        help_text = (
            "Bite-Size Reader\n\n"
            "Commands:\n"
            "- /help — show this help.\n"
            "- /summarize <URL> — summarize a URL.\n"
            "- /summarize_all <URLs> — summarize multiple URLs from one message.\n\n"
            "Usage:\n"
            "- You can simply send a URL (or several URLs) or forward a channel post — commands are optional.\n"
            "- You can also send /summarize and then a URL in the next message.\n"
            "- Multiple links in one message are supported; I can confirm or use /summarize_all to process immediately.\n\n"
            "Features:\n"
            "- Enhanced structured JSON output with schema validation\n"
            "- Intelligent model fallbacks for better reliability\n"
            "- Automatic content optimization based on model capabilities"
        )
        await self.safe_reply(message, help_text)

    async def send_welcome(self, message: Any) -> None:
        """Send welcome message to user."""
        welcome = (
            "Welcome to Bite-Size Reader!\n\n"
            "What I do:\n"
            "- Summarize articles from URLs using Firecrawl + OpenRouter.\n"
            "- Summarize forwarded channel posts.\n"
            "- Generate structured JSON summaries with enhanced reliability.\n\n"
            "How to use:\n"
            "- Send a URL directly, or use /summarize <URL>.\n"
            "- You can also send /summarize and then the URL in the next message.\n"
            "- For forwarded posts, use /summarize_forward and then forward a channel post.\n"
            '- Multiple links in one message are supported: I will ask "Process N links?" or use /summarize_all to process immediately.\n\n'
            "Notes:\n"
            "- I reply with a strict JSON object using advanced schema validation.\n"
            "- Intelligent model selection and fallbacks ensure high success rates.\n"
            "- Errors include an Error ID you can reference in logs."
        )
        await self.safe_reply(message, welcome)

    async def send_enhanced_summary_response(
        self, message: Any, summary_shaped: dict[str, Any], llm: Any, chunks: int | None = None
    ) -> None:
        """Send enhanced summary response with better formatting and metadata."""
        try:
            # Calculate processing metrics
            total_time = (llm.latency_ms or 0) / 1000.0
            tokens_used = (llm.tokens_prompt or 0) + (llm.tokens_completion or 0)
            cost_info = f" (${llm.cost_usd:.4f})" if llm.cost_usd else ""

            # Enhanced processing info
            processing_method = f"Chunked ({chunks} parts)" if chunks else "Single-pass"
            structured_info = ""
            if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                mode = getattr(llm, "structured_output_mode", "unknown")
                structured_info = f" • Schema: {mode.upper()}"

            preview_lines = [
                "🎉 **Enhanced Summary Complete!**",
                "",
                "⏱️ **Processing Stats:**",
                f"• Time: {total_time:.1f}s",
                f"• Tokens: {tokens_used:,}{cost_info}",
                f"• Model: {llm.model or 'unknown'}",
                f"• Method: {processing_method}{structured_info}",
                "",
                "📋 **TL;DR:**",
                str(summary_shaped.get("summary_250", "")).strip(),
            ]

            tags = summary_shaped.get("topic_tags") or []
            if tags:
                preview_lines.extend(["", "🏷️ **Tags:** " + " ".join(tags[:6])])

            ideas = [
                str(x).strip() for x in (summary_shaped.get("key_ideas") or []) if str(x).strip()
            ]
            if ideas:
                preview_lines.extend(["", "💡 **Key Ideas:**"])
                for idea in ideas[:3]:
                    preview_lines.append(f"• {idea}")

            # Add reading time if available
            reading_time = summary_shaped.get("estimated_reading_time_min")
            if reading_time:
                preview_lines.extend(["", f"⏱️ **Reading Time:** ~{reading_time} minutes"])

            preview_lines.extend(["", "📊 **Full JSON:**"])

            # Combine preview and JSON in one message
            combined_message = "\n".join(preview_lines)
            await self.safe_reply(message, combined_message)

            # Send JSON as separate code block for better formatting
            await self.reply_json(message, summary_shaped)

        except Exception:
            # Fallback to simpler format
            try:
                preview_lines = [
                    "🎉 **Summary Complete!**",
                    "",
                    "📋 **TL;DR:**",
                    str(summary_shaped.get("summary_250", "")).strip(),
                ]
                tags = summary_shaped.get("topic_tags") or []
                if tags:
                    preview_lines.append("🏷️ Tags: " + " ".join(tags[:6]))
                ideas = [
                    str(x).strip()
                    for x in (summary_shaped.get("key_ideas") or [])
                    if str(x).strip()
                ]
                if ideas:
                    preview_lines.append("💡 Key Ideas:")
                    for idea in ideas[:3]:
                        preview_lines.append(f"• {idea}")
                await self.safe_reply(message, "\n".join(preview_lines))
            except Exception:
                pass

            await self.reply_json(message, summary_shaped)

    async def send_forward_summary_response(
        self, message: Any, forward_shaped: dict[str, Any]
    ) -> None:
        """Send enhanced preview for forward flow."""
        try:
            preview_lines = [
                "🎉 **Enhanced Forward Summary Complete!**",
                "",
                "📋 **TL;DR:**",
                str(forward_shaped.get("summary_250", "")).strip(),
            ]
            tags = forward_shaped.get("topic_tags") or []
            if tags:
                preview_lines.append("🏷️ Tags: " + " ".join(tags[:6]))
            ideas = [
                str(x).strip() for x in (forward_shaped.get("key_ideas") or []) if str(x).strip()
            ]
            if ideas:
                preview_lines.append("💡 Key Ideas:")
                for idea in ideas[:3]:
                    preview_lines.append(f"• {idea}")
            await self.safe_reply(message, "\n".join(preview_lines))
        except Exception:
            pass

        await self.reply_json(message, forward_shaped)

    async def reply_json(self, message: Any, obj: dict) -> None:
        """Reply with JSON object, using file upload for large content."""
        pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        # Send large JSON as a file to avoid Telegram message size limits
        if len(pretty) > 3500:
            try:
                bio = io.BytesIO(pretty.encode("utf-8"))
                bio.name = "summary.json"
                msg_any: Any = message
                await msg_any.reply_document(bio, caption="📊 Enhanced Summary JSON")
                return
            except Exception as e:  # noqa: BLE001
                logger.error("reply_document_failed", extra={"error": str(e)})
        await self.safe_reply(message, f"```json\n{pretty}\n```")

    async def safe_reply(self, message: Any, text: str, *, parse_mode: str | None = None) -> None:
        """Safely reply to a message with error handling."""
        try:
            msg_any: Any = message
            if parse_mode:
                await msg_any.reply_text(text, parse_mode=parse_mode)
            else:
                await msg_any.reply_text(text)
            try:
                logger.debug("reply_text_sent", extra={"length": len(text)})
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            logger.error("reply_failed", extra={"error": str(e)})

    async def send_url_accepted_notification(
        self, message: Any, norm: str, correlation_id: str
    ) -> None:
        """Send URL accepted notification."""
        try:
            from urllib.parse import urlparse

            url_domain = urlparse(norm).netloc if norm else "unknown"
            await self.safe_reply(
                message,
                f"✅ **Request Accepted**\n"
                f"🌐 Domain: `{url_domain}`\n"
                f"🔗 URL: `{norm[:60]}{'...' if len(norm) > 60 else ''}`\n"
                f"📋 Status: Fetching content...\n"
                f"🤖 Enhanced: Structured output with smart fallbacks",
            )
        except Exception:
            pass

    async def send_firecrawl_start_notification(self, message: Any) -> None:
        """Send Firecrawl start notification."""
        try:
            await self.safe_reply(
                message,
                "🕷️ **Firecrawl Extraction**\n"
                "📡 Connecting to Firecrawl API...\n"
                "⏱️ This may take 10-30 seconds\n"
                "🔄 Enhanced processing pipeline active",
            )
        except Exception:
            pass

    async def send_firecrawl_success_notification(
        self, message: Any, excerpt_len: int, latency_sec: float
    ) -> None:
        """Send Firecrawl success notification."""
        try:
            await self.safe_reply(
                message,
                f"✅ **Content Extracted Successfully**\n"
                f"📊 Size: ~{excerpt_len:,} characters\n"
                f"⏱️ Extraction time: {latency_sec:.1f}s\n"
                f"🔄 Status: Preparing for enhanced AI analysis...",
            )
        except Exception:
            pass

    async def send_content_reuse_notification(self, message: Any) -> None:
        """Send content reuse notification."""
        try:
            await self.safe_reply(
                message,
                "♻️ **Reusing Cached Content**\n"
                "📊 Status: Content already extracted\n"
                "⚡ Proceeding to enhanced AI analysis...",
            )
        except Exception:
            pass

    async def send_html_fallback_notification(self, message: Any, content_len: int) -> None:
        """Send HTML fallback notification."""
        try:
            await self.safe_reply(
                message,
                f"🔄 **Content Processing Update**\n"
                f"📄 Markdown extraction was empty\n"
                f"🛠️ Using HTML content extraction\n"
                f"📊 Processing {content_len:,} characters...\n"
                f"🤖 Enhanced pipeline will optimize for best results",
            )
        except Exception:
            pass

    async def send_language_detection_notification(
        self, message: Any, detected: str | None, content_preview: str
    ) -> None:
        """Send language detection notification."""
        try:
            await self.safe_reply(
                message,
                f"🌍 **Language Detection**\n"
                f"📝 Detected: `{detected or 'unknown'}`\n"
                f"📄 Content preview:\n"
                f"```\n{content_preview}\n```\n"
                f"🤖 Status: Preparing enhanced AI analysis with structured outputs...",
            )
        except Exception:
            pass

    async def send_content_analysis_notification(
        self,
        message: Any,
        content_len: int,
        max_chars: int,
        enable_chunking: bool,
        chunks: list[str] | None,
        structured_output_mode: str,
    ) -> None:
        """Send content analysis notification."""
        try:
            if enable_chunking and content_len > max_chars and (chunks or []):
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters\n"
                    f"🔀 Processing: Chunked analysis ({len(chunks or [])} chunks)\n"
                    f"🤖 Method: Advanced structured output with schema validation\n"
                    f"⚡ Status: Sending to AI model with smart fallbacks...",
                )
            elif not enable_chunking and content_len > max_chars:
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters (exceeds {max_chars:,} adaptive threshold)\n"
                    f"🔀 Processing: Single-pass (chunking disabled)\n"
                    f"🤖 Method: Enhanced structured output with intelligent fallbacks\n"
                    f"⚡ Status: Sending to AI model...",
                )
            else:
                await self.safe_reply(
                    message,
                    f"📚 **Enhanced Content Analysis**\n"
                    f"📊 Length: {content_len:,} characters\n"
                    f"🔀 Processing: Single-pass summary\n"
                    f"🤖 Method: Structured output with schema validation\n"
                    f"⚡ Status: Sending to AI model...",
                )
        except Exception:
            pass

    async def send_llm_start_notification(
        self, message: Any, model: str, content_len: int, structured_output_mode: str
    ) -> None:
        """Send LLM start notification."""
        try:
            await self.safe_reply(
                message,
                f"🤖 **Enhanced AI Analysis Starting**\n"
                f"🧠 Model: `{model}`\n"
                f"📊 Content: {content_len:,} characters\n"
                f"🔧 Mode: {structured_output_mode.upper()} with smart fallbacks\n"
                f"⏱️ This may take 30-60 seconds...",
            )
        except Exception:
            pass

    async def send_llm_completion_notification(
        self, message: Any, llm: Any, correlation_id: str
    ) -> None:
        """Send LLM completion notification."""
        try:
            model_name = llm.model or "unknown"
            latency_sec = (llm.latency_ms or 0) / 1000.0

            if llm.status == "ok":
                # Success message with enhanced details
                tokens_used = (llm.tokens_prompt or 0) + (llm.tokens_completion or 0)
                cost_info = f" (${llm.cost_usd:.4f})" if llm.cost_usd else ""
                structured_info = ""
                if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                    mode = getattr(llm, "structured_output_mode", "unknown")
                    structured_info = f"\n🔧 Structured Output: {mode.upper()}"

                await self.safe_reply(
                    message,
                    f"🤖 **Enhanced AI Analysis Complete**\n"
                    f"✅ Status: Success\n"
                    f"🧠 Model: `{model_name}`\n"
                    f"⏱️ Processing time: {latency_sec:.1f}s\n"
                    f"🔢 Tokens used: {tokens_used:,}{cost_info}{structured_info}\n"
                    f"📋 Status: Generating enhanced summary...",
                )
            else:
                # Enhanced error message
                await self.safe_reply(
                    message,
                    f"🤖 **Enhanced AI Analysis Failed**\n"
                    f"❌ Status: Error\n"
                    f"🧠 Model: `{model_name}`\n"
                    f"⏱️ Processing time: {latency_sec:.1f}s\n"
                    f"🚨 Error: {llm.error_text or 'Unknown error'}\n"
                    f"🔄 Smart fallbacks: Active\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
        except Exception:
            pass

    async def send_forward_accepted_notification(self, message: Any, title: str) -> None:
        """Send forward request accepted notification."""
        try:
            await self.safe_reply(
                message,
                "✅ **Forward Request Accepted**\n"
                f"📺 Channel: {title}\n"
                "🤖 Enhanced processing with structured outputs...\n"
                "📋 Status: Generating summary...",
            )
        except Exception:
            pass

    async def send_forward_language_notification(self, message: Any, detected: str | None) -> None:
        """Send forward language detection notification."""
        try:
            await self.safe_reply(
                message,
                f"🌍 **Language Detection**\n"
                f"📝 Detected: `{detected or 'unknown'}`\n"
                f"🤖 Processing with enhanced structured outputs...\n"
                f"⚡ Status: Sending to AI model...",
            )
        except Exception:
            pass

    async def send_forward_completion_notification(self, message: Any, llm: Any) -> None:
        """Send forward completion notification."""
        try:
            status_emoji = "✅" if llm.status == "ok" else "❌"
            latency_sec = (llm.latency_ms or 0) / 1000.0
            structured_info = ""
            if hasattr(llm, "structured_output_used") and llm.structured_output_used:
                mode = getattr(llm, "structured_output_mode", "unknown")
                structured_info = f"\n🔧 Schema: {mode.upper()}"

            await self.safe_reply(
                message,
                f"🤖 **Enhanced AI Analysis Complete**\n"
                f"{status_emoji} Status: {'Success' if llm.status == 'ok' else 'Error'}\n"
                f"⏱️ Time: {latency_sec:.1f}s{structured_info}\n"
                f"📋 Status: {'Generating summary...' if llm.status == 'ok' else 'Processing error...'}",
            )
        except Exception:
            pass

    async def send_error_notification(
        self, message: Any, error_type: str, correlation_id: str, details: str | None = None
    ) -> None:
        """Send error notification with enhanced formatting."""
        try:
            if error_type == "firecrawl_error":
                await self.safe_reply(
                    message,
                    f"❌ **Content Extraction Failed**\n"
                    f"🚨 Unable to extract readable content\n"
                    f"🆔 Error ID: `{correlation_id}`\n\n"
                    f"💡 **Possible Solutions:**\n"
                    f"• Try a different URL\n"
                    f"• Check if content is publicly accessible\n"
                    f"• Ensure URL points to text-based content",
                )
            elif error_type == "empty_content":
                await self.safe_reply(
                    message,
                    f"❌ **Content Extraction Failed**\n\n"
                    f"🚨 **Possible Causes:**\n"
                    f"• Website blocking automated access\n"
                    f"• Content behind paywall/login\n"
                    f"• Non-text content (images, videos)\n"
                    f"• Temporary server issues\n"
                    f"• Invalid or inaccessible URL\n\n"
                    f"💡 **Suggestions:**\n"
                    f"• Try a different URL\n"
                    f"• Check if content is publicly accessible\n"
                    f"• Ensure URL points to text-based content\n\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
            elif error_type == "processing_failed":
                await self.safe_reply(
                    message,
                    f"❌ **Enhanced Processing Failed**\n"
                    f"🚨 Invalid summary format despite smart fallbacks\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
            elif error_type == "llm_error":
                await self.safe_reply(
                    message,
                    f"❌ **Enhanced Processing Failed**\n"
                    f"🚨 LLM error despite smart fallbacks\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
            else:
                # Generic error
                await self.safe_reply(
                    message,
                    f"❌ **Error Occurred**\n"
                    f"🚨 {details or 'Unknown error'}\n"
                    f"🆔 Error ID: `{correlation_id}`",
                )
        except Exception:
            pass
