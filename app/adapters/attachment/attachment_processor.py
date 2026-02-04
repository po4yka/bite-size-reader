"""Attachment processor for images and PDFs sent to the bot."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.adapters.attachment.image_extractor import ImageExtractor
from app.adapters.attachment.pdf_extractor import PDFExtractor
from app.adapters.attachment.vision_messages import (
    build_multi_image_vision_messages,
    build_text_with_images_messages,
    build_vision_messages,
)
from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)
from app.core.lang import LANG_RU, choose_language, detect_language
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# Maximum text content length for PDF text extraction path
_MAX_PDF_TEXT_CHARS = 45_000


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_prompt(prompt_name: str, lang: str) -> str:
    """Load a prompt file by name and language."""
    lang = lang if lang in ("en", "ru") else "en"
    fname = f"{prompt_name}_{lang}.txt"
    path = _PROMPT_DIR / fname
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        # Fall back to English
        fallback = _PROMPT_DIR / f"{prompt_name}_en.txt"
        return fallback.read_text(encoding="utf-8").strip()


class AttachmentProcessor:
    """Processes image and PDF attachments sent to the bot."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.user_repo = SqliteUserRepositoryAdapter(db)
        self._workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

    async def handle_attachment_flow(
        self,
        message: Any,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Main entry point for processing an attachment message."""
        file_path: str | None = None
        try:
            # Classify the attachment
            file_type, mime_type, file_name = self._classify_attachment(message)
            if not file_type:
                await self.response_formatter.safe_reply(
                    message,
                    "This file type is not yet supported. Supported: images, PDFs, text files.",
                )
                return

            # Check file size limits
            size_error = self._check_size_limits(message, file_type)
            if size_error:
                await self.response_formatter.safe_reply(message, size_error)
                return

            # Notify user we're processing
            type_label = "image" if file_type == "image" else "PDF document"
            await self.response_formatter.safe_reply(
                message,
                f"Processing {type_label}...",
            )

            # Download the file
            file_path = await self._download_attachment(message)
            if not file_path:
                await self.response_formatter.send_error_notification(
                    message,
                    "processing_failed",
                    correlation_id or "unknown",
                    details="Failed to download attachment",
                )
                return

            # Get caption for context
            caption = (getattr(message, "caption", None) or "").strip() or None

            # Create request record
            req_id = await self._create_request(message, correlation_id, file_type)

            # Detect language from caption or default
            text_for_lang = caption or ""
            detected = detect_language(text_for_lang) if text_for_lang else "en"
            chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)

            # Create attachment processing record
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
            await self._create_attachment_record(
                req_id=req_id,
                file_type=file_type,
                mime_type=mime_type,
                file_name=file_name,
                file_size=file_size,
            )

            # Process based on type
            if file_type == "image":
                result = await self._process_image(
                    file_path, caption, chosen_lang, req_id, correlation_id, interaction_id, message
                )
            else:
                result = await self._process_pdf(
                    file_path, caption, chosen_lang, req_id, correlation_id, interaction_id, message
                )

            if result:
                # Update attachment record with success details
                await self._update_attachment_status(req_id, "completed", result)

                # Send formatted summary
                await self.response_formatter.send_forward_summary_response(
                    message,
                    result,
                    summary_id=f"req:{req_id}",
                )

                if interaction_id:
                    await async_safe_update_user_interaction(
                        self.user_repo,
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="summary",
                        request_id=req_id,
                        logger_=logger,
                    )

        except Exception as exc:
            logger.exception(
                "attachment_flow_error",
                extra={"error": str(exc), "cid": correlation_id},
            )
            try:
                await self.response_formatter.send_error_notification(
                    message,
                    "processing_failed",
                    correlation_id or "unknown",
                )
            except Exception:
                logger.debug("attachment_error_notification_failed", extra={"cid": correlation_id})
        finally:
            # Clean up temp file
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except OSError as exc:
                    logger.warning(
                        "attachment_cleanup_failed",
                        extra={"path": file_path, "error": str(exc)},
                    )

    def _classify_attachment(self, message: Any) -> tuple[str | None, str | None, str | None]:
        """Classify the attachment type. Returns (file_type, mime_type, file_name) or (None, None, None)."""
        # Telegram photo (always an image)
        if getattr(message, "photo", None):
            return "image", "image/jpeg", None

        doc = getattr(message, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "") or ""
            fname = getattr(doc, "file_name", None)
            if mime.startswith("image/"):
                return "image", mime, fname
            if mime == "application/pdf":
                return "pdf", mime, fname

        return None, None, None

    def _check_size_limits(self, message: Any, file_type: str) -> str | None:
        """Check file size against configured limits. Returns error message or None."""
        attachment_cfg = self.cfg.attachment
        file_size = None

        if getattr(message, "photo", None):
            # Telegram sends multiple sizes; the last one is the largest
            photo = message.photo
            file_size = getattr(photo, "file_size", None)
        elif getattr(message, "document", None):
            file_size = getattr(message.document, "file_size", None)

        if file_size is None:
            return None

        max_bytes = (
            attachment_cfg.max_image_size_mb * 1024 * 1024
            if file_type == "image"
            else attachment_cfg.max_pdf_size_mb * 1024 * 1024
        )

        if file_size > max_bytes:
            max_mb = (
                attachment_cfg.max_image_size_mb
                if file_type == "image"
                else attachment_cfg.max_pdf_size_mb
            )
            label = "Image" if file_type == "image" else "PDF"
            return f"{label} too large (max {max_mb}MB)."

        return None

    async def _download_attachment(self, message: Any) -> str | None:
        """Download the attachment to a temp file. Returns the file path or None."""
        storage_path = self.cfg.attachment.storage_path
        os.makedirs(storage_path, exist_ok=True)

        try:
            path = await message.download(file_name=tempfile.mktemp(dir=storage_path))
            return str(path) if path else None
        except Exception as exc:
            logger.exception(
                "attachment_download_failed",
                extra={"error": str(exc)},
            )
            return None

    async def _create_request(
        self, message: Any, correlation_id: str | None, file_type: str
    ) -> int:
        """Create a request record for the attachment."""
        chat_obj = getattr(message, "chat", None)
        chat_id = _coerce_int(getattr(chat_obj, "id", None) if chat_obj else None)
        from_user = getattr(message, "from_user", None)
        user_id = _coerce_int(getattr(from_user, "id", None) if from_user else None)
        msg_id = _coerce_int(getattr(message, "id", getattr(message, "message_id", None)))

        return await self.request_repo.async_create_request(
            type_=file_type,
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_message_id=msg_id,
            content_text=getattr(message, "caption", None),
        )

    async def _create_attachment_record(
        self,
        *,
        req_id: int,
        file_type: str,
        mime_type: str | None,
        file_name: str | None,
        file_size: int | None,
    ) -> None:
        """Create an AttachmentProcessing record."""
        import asyncio

        from app.db.models import AttachmentProcessing

        def _create() -> None:
            AttachmentProcessing.create(
                request=req_id,
                file_type=file_type,
                mime_type=mime_type,
                file_name=file_name,
                file_size_bytes=file_size,
                status="processing",
            )

        await asyncio.to_thread(_create)

    async def _update_attachment_status(
        self, req_id: int, status: str, result: dict[str, Any] | None = None
    ) -> None:
        """Update the attachment processing record status."""
        import asyncio

        from app.db.models import AttachmentProcessing

        def _update() -> None:
            try:
                record = AttachmentProcessing.get(AttachmentProcessing.request == req_id)
                record.status = status
                if result:
                    record.extracted_text_length = len(result.get("tldr", ""))
                record.save()
            except AttachmentProcessing.DoesNotExist:
                pass

        await asyncio.to_thread(_update)

    async def _process_image(
        self,
        file_path: str,
        caption: str | None,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
        message: Any,
    ) -> dict[str, Any] | None:
        """Process an image attachment via vision LLM."""
        attachment_cfg = self.cfg.attachment

        try:
            image_content = ImageExtractor.extract(
                file_path, max_dimension=attachment_cfg.image_max_dimension
            )
        except ValueError as exc:
            logger.warning(
                "image_extraction_failed",
                extra={"error": str(exc), "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(message, f"Could not process image: {exc}")
            return None

        system_prompt = _load_prompt("image_analysis", chosen_lang)

        lang_label = "Russian" if chosen_lang == LANG_RU else "English"
        user_text = (
            caption
            or f"Analyze this image and provide a structured summary. Respond in {lang_label}."
        )
        if caption:
            user_text = f"{caption}\n\nRespond in {lang_label}."

        messages = build_vision_messages(system_prompt, image_content.data_uri, caption=user_text)

        return await self._run_llm_workflow(
            messages=messages,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            chosen_lang=chosen_lang,
            message=message,
            model_override=attachment_cfg.vision_model,
        )

    async def _process_pdf(
        self,
        file_path: str,
        caption: str | None,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
        message: Any,
    ) -> dict[str, Any] | None:
        """Process a PDF attachment."""
        attachment_cfg = self.cfg.attachment

        try:
            pdf_content = PDFExtractor.extract(
                file_path,
                max_pages=attachment_cfg.max_pdf_pages,
                max_vision_pages=attachment_cfg.max_vision_pages_per_pdf,
                image_max_dimension=attachment_cfg.image_max_dimension,
            )
        except ValueError as exc:
            logger.warning(
                "pdf_extraction_failed",
                extra={"error": str(exc), "cid": correlation_id},
            )
            await self.response_formatter.safe_reply(message, f"Could not process PDF: {exc}")
            return None

        # Update attachment record with PDF metadata
        await self._update_pdf_metadata(req_id, pdf_content)

        system_prompt = _load_prompt("pdf_analysis", chosen_lang)
        lang_label = "Russian" if chosen_lang == LANG_RU else "English"

        model_override: str | None = None

        if pdf_content.is_scanned and pdf_content.image_pages:
            # Scanned PDF: use vision model on rendered pages
            model_override = attachment_cfg.vision_model
            image_uris = [img.data_uri for img in pdf_content.image_pages]

            if pdf_content.text.strip():
                # Hybrid: has some text plus scanned pages
                text = pdf_content.text[:_MAX_PDF_TEXT_CHARS]
                user_caption = caption or f"Summarize this PDF document. Respond in {lang_label}."
                if caption:
                    user_caption = f"{caption}\n\nRespond in {lang_label}."
                messages = build_text_with_images_messages(
                    system_prompt, text, image_uris, caption=user_caption
                )
            else:
                # Fully scanned: vision only
                user_caption = (
                    caption
                    or f"Analyze these PDF pages and provide a structured summary. Respond in {lang_label}."
                )
                if caption:
                    user_caption = f"{caption}\n\nRespond in {lang_label}."
                messages = build_multi_image_vision_messages(
                    system_prompt, image_uris, caption=user_caption
                )
        else:
            # Text-rich PDF: use regular text-based summarization
            text = pdf_content.text[:_MAX_PDF_TEXT_CHARS]
            truncation_note = ""
            if pdf_content.truncated:
                truncation_note = f"\n\n[Document truncated: showing {self.cfg.attachment.max_pdf_pages} of {pdf_content.page_count} pages]"

            user_content = f"Summarize the following PDF document to the specified JSON schema. Respond in {lang_label}.\n\n{text}{truncation_note}"
            if caption:
                user_content = f"User context: {caption}\n\n{user_content}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

        return await self._run_llm_workflow(
            messages=messages,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            chosen_lang=chosen_lang,
            message=message,
            model_override=model_override,
        )

    async def _update_pdf_metadata(self, req_id: int, pdf_content: Any) -> None:
        """Update attachment record with PDF-specific metadata."""
        import asyncio

        from app.db.models import AttachmentProcessing

        def _update() -> None:
            try:
                record = AttachmentProcessing.get(AttachmentProcessing.request == req_id)
                record.page_count = pdf_content.page_count
                record.extracted_text_length = len(pdf_content.text)
                record.vision_used = bool(pdf_content.image_pages)
                record.vision_pages_count = (
                    len(pdf_content.image_pages) if pdf_content.image_pages else None
                )
                record.processing_method = (
                    "hybrid"
                    if pdf_content.image_pages and pdf_content.text.strip()
                    else "vision"
                    if pdf_content.is_scanned
                    else "text_extraction"
                )
                record.save()
            except AttachmentProcessing.DoesNotExist:
                pass

        await asyncio.to_thread(_update)

    async def _run_llm_workflow(
        self,
        *,
        messages: list[dict[str, Any]],
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
        chosen_lang: str,
        message: Any,
        model_override: str | None = None,
    ) -> dict[str, Any] | None:
        """Run the standard LLM summary workflow."""
        max_tokens = 6144

        response_format = self._workflow.build_structured_response_format()

        # Build the request config, including model_override for vision models
        request_kwargs: dict[str, Any] = {
            "messages": messages,
            "response_format": response_format,
            "max_tokens": max_tokens,
            "temperature": self.cfg.openrouter.temperature,
            "top_p": self.cfg.openrouter.top_p,
        }
        if model_override:
            request_kwargs["model_override"] = model_override

        requests = [LLMRequestConfig(**request_kwargs)]

        repair_context = LLMRepairContext(
            base_messages=messages,
            repair_response_format=self._workflow.build_structured_response_format(),
            repair_max_tokens=max_tokens,
            default_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON "
                "that matches the schema exactly."
            ),
        )

        async def _on_completion(llm_result: Any, _: LLMRequestConfig) -> None:
            await self.response_formatter.send_forward_completion_notification(message, llm_result)

        async def _on_llm_error(llm_result: Any, details: str | None) -> None:
            await self.response_formatter.send_error_notification(
                message,
                "llm_error",
                correlation_id or "unknown",
                details=details,
            )

        async def _on_processing_failure() -> None:
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
            )

        notifications = LLMWorkflowNotifications(
            completion=_on_completion,
            llm_error=_on_llm_error,
            repair_failure=_on_processing_failure,
            parsing_failure=_on_processing_failure,
        )

        interaction_config = LLMInteractionConfig(
            interaction_id=interaction_id,
            success_kwargs={
                "response_sent": True,
                "response_type": "summary",
                "request_id": req_id,
            },
            llm_error_builder=lambda llm_result, details: {
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": details
                or f"LLM error: {llm_result.error_text or 'Unknown error'}",
                "request_id": req_id,
            },
            repair_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
            parsing_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
        )

        persistence = LLMSummaryPersistenceSettings(
            lang=chosen_lang,
            is_read=True,
        )

        return await self._workflow.execute_summary_workflow(
            message=message,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_config=interaction_config,
            persistence=persistence,
            repair_context=repair_context,
            requests=requests,
            notifications=notifications,
        )
