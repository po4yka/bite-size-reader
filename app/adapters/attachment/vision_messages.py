"""Build multipart vision messages for OpenRouter-compatible LLM calls."""

from __future__ import annotations

from typing import Any


def build_vision_messages(
    system_prompt: str,
    image_data_uri: str,
    *,
    caption: str | None = None,
) -> list[dict[str, Any]]:
    """Build OpenRouter-compatible multipart messages for vision analysis.

    Args:
        system_prompt: System prompt with analysis instructions.
        image_data_uri: Base64-encoded data URI (e.g., "data:image/jpeg;base64,...").
        caption: Optional user-provided caption/context for the image.

    Returns:
        List of message dicts with multipart content for vision models.
    """
    text_instruction = caption or "Analyze this image and provide a structured summary."

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_instruction},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        },
    ]


def build_multi_image_vision_messages(
    system_prompt: str,
    image_data_uris: list[str],
    *,
    caption: str | None = None,
) -> list[dict[str, Any]]:
    """Build multipart messages with multiple images (e.g., rendered PDF pages).

    Args:
        system_prompt: System prompt with analysis instructions.
        image_data_uris: List of base64-encoded data URIs.
        caption: Optional user-provided caption/context.

    Returns:
        List of message dicts with multiple image parts for vision models.
    """
    text_instruction = caption or "Analyze these document pages and provide a structured summary."

    content_parts: list[dict[str, Any]] = [{"type": "text", "text": text_instruction}]
    for uri in image_data_uris:
        content_parts.append({"type": "image_url", "image_url": {"url": uri}})

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_parts},
    ]


def build_text_with_images_messages(
    system_prompt: str,
    text_content: str,
    image_data_uris: list[str],
    *,
    caption: str | None = None,
) -> list[dict[str, Any]]:
    """Build messages combining extracted text and rendered page images.

    Used for hybrid PDFs that have both text and scanned/image-heavy pages.

    Args:
        system_prompt: System prompt with analysis instructions.
        text_content: Extracted text from the PDF.
        image_data_uris: Data URIs for rendered sparse/scanned pages.
        caption: Optional user-provided caption/context.

    Returns:
        List of message dicts combining text and image content.
    """
    text_parts = []
    if caption:
        text_parts.append(f"User context: {caption}\n\n")
    text_parts.append(f"Extracted text:\n{text_content}")

    content_parts: list[dict[str, Any]] = [
        {"type": "text", "text": "".join(text_parts)},
    ]
    for uri in image_data_uris:
        content_parts.append({"type": "image_url", "image_url": {"url": uri}})

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_parts},
    ]
