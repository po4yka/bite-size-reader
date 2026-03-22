"""Attachment classification, extraction, and prompt assembly helpers."""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import TYPE_CHECKING, Any

from app.adapters.attachment._attachment_shared import _MAX_PDF_TEXT_CHARS, load_prompt
from app.adapters.attachment.image_extractor import ImageExtractor
from app.adapters.attachment.pdf_extractor import PDFExtractor
from app.adapters.attachment.vision_messages import (
    build_multi_image_vision_messages,
    build_text_with_images_messages,
    build_vision_messages,
)
from app.core.lang import LANG_AUTO, LANG_RU, choose_language, detect_language

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.attachment._attachment_llm import AttachmentLLMWorkflowService
    from app.adapters.attachment._attachment_persistence import AttachmentPersistenceService
    from app.adapters.attachment._attachment_shared import AttachmentProcessorContext


class AttachmentContentService:
    """Processes downloaded attachments into LLM-ready requests."""

    def __init__(
        self,
        context: AttachmentProcessorContext,
        *,
        persistence: AttachmentPersistenceService,
        workflow: AttachmentLLMWorkflowService,
    ) -> None:
        self._context = context
        self._persistence = persistence
        self._workflow = workflow

    def classify_attachment(self, message: Any) -> tuple[str | None, str | None, str | None]:
        """Classify the attachment type."""
        if getattr(message, "photo", None):
            return "image", "image/jpeg", None

        doc = getattr(message, "document", None)
        if not doc:
            return None, None, None

        mime = getattr(doc, "mime_type", "") or ""
        fname = getattr(doc, "file_name", None)
        if mime.startswith("image/"):
            return "image", mime, fname
        if mime == "application/pdf":
            return "pdf", mime, fname
        return None, None, None

    def check_size_limits(self, message: Any, file_type: str) -> str | None:
        """Check the attachment size against configuration limits."""
        attachment_cfg = self._context.cfg.attachment
        file_size = None
        if getattr(message, "photo", None):
            file_size = getattr(message.photo, "file_size", None)
        elif getattr(message, "document", None):
            file_size = getattr(message.document, "file_size", None)

        if file_size is None:
            return None

        max_bytes = (
            attachment_cfg.max_image_size_mb * 1024 * 1024
            if file_type == "image"
            else attachment_cfg.max_pdf_size_mb * 1024 * 1024
        )
        if file_size <= max_bytes:
            return None

        max_mb = (
            attachment_cfg.max_image_size_mb
            if file_type == "image"
            else attachment_cfg.max_pdf_size_mb
        )
        label = "Image" if file_type == "image" else "PDF"
        return f"{label} too large (max {max_mb}MB)."

    async def download_attachment(self, message: Any) -> str | None:
        """Download the attachment to a temp file."""
        storage_path = self._context.cfg.attachment.storage_path
        os.makedirs(storage_path, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=storage_path)
            os.close(fd)
            path = await message.download(file_name=tmp_path)
            return str(path) if path else None
        except Exception as exc:
            self._context.logger.exception(
                "attachment_download_failed",
                extra={"error": str(exc)},
            )
            return None

    def choose_attachment_language(self, caption: str | None, message: Any) -> str:
        """Determine response language for attachment analysis."""
        text_for_lang = caption or ""
        user_lang_code = getattr(getattr(message, "from_user", None), "language_code", None)
        user_lang = user_lang_code[:2] if user_lang_code else "en"
        detected = detect_language(text_for_lang) if text_for_lang else user_lang
        return choose_language(self._context.cfg.runtime.preferred_lang, detected)

    async def process_downloaded_attachment(
        self,
        *,
        message: Any,
        file_path: str,
        file_type: str,
        mime_type: str | None,
        file_name: str | None,
        caption: str | None,
        correlation_id: str | None,
        interaction_id: int | None,
        status_updater: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Create records and dispatch attachment analysis."""
        req_id = await self._persistence.create_request(message, correlation_id, file_type)
        chosen_lang = self.choose_attachment_language(caption, message)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None
        await self._persistence.create_attachment_record(
            req_id=req_id,
            file_type=file_type,
            mime_type=mime_type,
            file_name=file_name,
            file_size=file_size,
        )

        if file_type == "image":
            result = await self.process_image(
                file_path=file_path,
                caption=caption,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                message=message,
                status_updater=status_updater,
            )
        else:
            result = await self.process_pdf(
                file_path=file_path,
                caption=caption,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                interaction_id=interaction_id,
                message=message,
                status_updater=status_updater,
            )
        return req_id, result

    async def process_image(
        self,
        *,
        file_path: str,
        caption: str | None,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
        message: Any,
        status_updater: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any] | None:
        """Process an image attachment via the vision model."""
        attachment_cfg = self._context.cfg.attachment
        if status_updater:
            await status_updater("🖼 <b>Processing image...</b>")

        try:
            image_content = ImageExtractor.extract(
                file_path,
                max_dimension=attachment_cfg.image_max_dimension,
            )
        except ValueError as exc:
            self._context.logger.warning(
                "image_extraction_failed",
                extra={"error": str(exc), "cid": correlation_id},
            )
            await self._context.response_formatter.safe_reply(
                message,
                f"Could not process image: {exc}",
            )
            return None

        system_prompt = load_prompt("image_analysis", chosen_lang)
        lang_label = "Russian" if chosen_lang == LANG_RU else "English"
        user_text = (
            caption
            or f"Analyze this image and provide a structured summary. Respond in {lang_label}."
        )
        if caption:
            user_text = f"{caption}\n\nRespond in {lang_label}."

        messages = build_vision_messages(system_prompt, image_content.data_uri, caption=user_text)
        return await self._workflow.run_summary_workflow(
            messages=messages,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            chosen_lang=chosen_lang,
            message=message,
            model_override=attachment_cfg.vision_model,
            status_updater=status_updater,
        )

    async def process_pdf(
        self,
        *,
        file_path: str,
        caption: str | None,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
        message: Any,
        status_updater: Callable[[str], Awaitable[None]] | None = None,
    ) -> dict[str, Any] | None:
        """Process a PDF attachment."""
        attachment_cfg = self._context.cfg.attachment
        try:

            async def on_pdf_progress(text: str) -> None:
                if status_updater:
                    await status_updater(f"📄 <b>PDF:</b> {text}")

            loop = asyncio.get_running_loop()
            pdf_content = await asyncio.to_thread(
                PDFExtractor.extract,
                file_path,
                max_pages=attachment_cfg.max_pdf_pages,
                max_vision_pages=attachment_cfg.max_vision_pages_per_pdf,
                image_max_dimension=attachment_cfg.image_max_dimension,
                on_progress=lambda text: asyncio.run_coroutine_threadsafe(
                    on_pdf_progress(text),
                    loop,
                ),
            )
        except ValueError as exc:
            self._context.logger.warning(
                "pdf_extraction_failed",
                extra={"error": str(exc), "cid": correlation_id},
            )
            await self._context.response_formatter.safe_reply(
                message,
                f"Could not process PDF: {exc}",
            )
            return None

        await self._persistence.update_pdf_metadata(req_id, pdf_content)

        if not caption and self._context.cfg.runtime.preferred_lang == LANG_AUTO:
            content_text = pdf_content.text[:2000]
            if content_text.strip():
                detected = detect_language(content_text)
                chosen_lang = choose_language(self._context.cfg.runtime.preferred_lang, detected)

        metadata_header = self.build_pdf_metadata_header(pdf_content)
        system_prompt = load_prompt("pdf_analysis", chosen_lang)
        lang_label = "Russian" if chosen_lang == LANG_RU else "English"
        model_override: str | None = None

        all_image_uris = [img.data_uri for img in pdf_content.image_pages]
        for image in pdf_content.embedded_images:
            if len(all_image_uris) >= 10:
                break
            all_image_uris.append(image.data_uri)

        if all_image_uris:
            model_override = attachment_cfg.vision_model

        if pdf_content.is_scanned and pdf_content.image_pages:
            messages = self._build_scanned_pdf_messages(
                pdf_content=pdf_content,
                metadata_header=metadata_header,
                system_prompt=system_prompt,
                image_uris=all_image_uris,
                caption=caption,
                lang_label=lang_label,
            )
        else:
            messages = self._build_text_pdf_messages(
                pdf_content=pdf_content,
                metadata_header=metadata_header,
                system_prompt=system_prompt,
                image_uris=all_image_uris,
                caption=caption,
                lang_label=lang_label,
            )

        return await self._workflow.run_summary_workflow(
            messages=messages,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            chosen_lang=chosen_lang,
            message=message,
            model_override=model_override,
            status_updater=status_updater,
        )

    def build_pdf_metadata_header(self, pdf_content: Any) -> str:
        """Build a compact metadata header for PDF prompts."""
        metadata_parts: list[str] = []
        metadata = pdf_content.metadata
        if metadata.get("title"):
            metadata_parts.append(f"Title: {metadata['title']}")
        if metadata.get("author"):
            metadata_parts.append(f"Author: {metadata['author']}")
        if metadata.get("subject"):
            metadata_parts.append(f"Subject: {metadata['subject']}")
        if metadata.get("keywords"):
            metadata_parts.append(f"Keywords: {metadata['keywords']}")

        if pdf_content.toc:
            toc_lines: list[str] = []
            for level, title, page in pdf_content.toc[:30]:
                indent = "  " * (level - 1)
                toc_lines.append(f"{indent}- {title} (page {page})")
            if toc_lines:
                metadata_parts.append("Table of Contents:\n" + "\n".join(toc_lines))

        if not metadata_parts:
            return ""
        return "Document Metadata:\n" + "\n".join(metadata_parts) + "\n\n"

    def _build_scanned_pdf_messages(
        self,
        *,
        pdf_content: Any,
        metadata_header: str,
        system_prompt: str,
        image_uris: list[str],
        caption: str | None,
        lang_label: str,
    ) -> list[dict[str, Any]]:
        if pdf_content.text.strip():
            text = f"{metadata_header}{pdf_content.text[:_MAX_PDF_TEXT_CHARS]}"
            user_caption = caption or f"Summarize this PDF document. Respond in {lang_label}."
            if caption:
                user_caption = f"{caption}\n\nRespond in {lang_label}."
            return build_text_with_images_messages(
                system_prompt,
                text,
                image_uris,
                caption=user_caption,
            )

        user_caption = (
            caption
            or f"Analyze these PDF pages and provide a structured summary. Respond in {lang_label}."
        )
        if caption:
            user_caption = f"{caption}\n\nRespond in {lang_label}."
        scanned_caption = f"{metadata_header}{user_caption}" if metadata_header else user_caption
        return build_multi_image_vision_messages(system_prompt, image_uris, caption=scanned_caption)

    def _build_text_pdf_messages(
        self,
        *,
        pdf_content: Any,
        metadata_header: str,
        system_prompt: str,
        image_uris: list[str],
        caption: str | None,
        lang_label: str,
    ) -> list[dict[str, Any]]:
        text = f"{metadata_header}{pdf_content.text[:_MAX_PDF_TEXT_CHARS]}"
        truncation_note = ""
        if pdf_content.truncated:
            truncation_note = (
                "\n\n[Document truncated: showing "
                f"{self._context.cfg.attachment.max_pdf_pages} of {pdf_content.page_count} pages]"
            )

        user_content = (
            "Summarize the following PDF document to the specified JSON schema. "
            f"Respond in {lang_label}.\n\n{text}{truncation_note}"
        )
        if caption:
            user_content = f"User context: {caption}\n\n{user_content}"

        if not image_uris:
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

        return build_text_with_images_messages(
            system_prompt,
            text,
            image_uris,
            caption=caption,
        )
