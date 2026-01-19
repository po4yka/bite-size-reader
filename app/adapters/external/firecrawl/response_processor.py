"""Response processing for Firecrawl API responses.

This module provides:
- Success response handling
- Error detection in response bodies
- Content field extraction
- Metadata enrichment
"""

from __future__ import annotations

from typing import Any


class ResponseProcessor:
    """Processes and extracts content from Firecrawl API responses."""

    @staticmethod
    def coerce_success(raw_success: Any) -> bool | None:
        """Coerce raw success field to boolean or None.

        Args:
            raw_success: Raw success value from response

        Returns:
            Boolean value, or None if raw_success is None
        """
        if isinstance(raw_success, bool):
            return raw_success
        if raw_success is None:
            return None
        return bool(raw_success)

    @staticmethod
    def detect_error_in_body(data: dict[str, Any]) -> tuple[bool, str | None]:
        """Detect error conditions in response body.

        Checks for:
        - Explicit error field with content
        - success=false with no content
        - Empty data array
        - All data items having errors
        - Data object with error
        - No content returned (no markdown, html, or data)

        Args:
            data: Parsed response data dictionary

        Returns:
            Tuple of (has_error, error_message)
        """
        response_error = data.get("error")
        if response_error and str(response_error).strip():
            return True, str(response_error)

        if data.get("success") is False:
            return True, data.get("message") or "Request failed (success=false)"

        if "data" in data and isinstance(data["data"], list):
            if not data["data"]:
                return True, "No data returned in response"
            all_errors = all(item.get("error") for item in data["data"] if isinstance(item, dict))
            if all_errors and len(data["data"]) > 0:
                return True, data["data"][0].get("error") or "All data items have errors"

        if isinstance(data.get("data"), dict) and data["data"].get("error"):
            return True, data["data"].get("error") or "Data object error"

        if not data.get("markdown") and not data.get("html") and "data" not in data:
            return True, "No content returned"

        return False, None

    @staticmethod
    def extract_content_fields(
        data: dict[str, Any],
    ) -> tuple[str | None, str | None, dict[str, Any] | None, dict[str, Any] | list[Any] | None]:
        """Extract content fields from response data.

        Handles various response formats:
        - Direct markdown/html at top level
        - Content nested in data[0] (array format)
        - Content nested in data (object format)

        Args:
            data: Parsed response data dictionary

        Returns:
            Tuple of (content_markdown, content_html, metadata, links)
        """
        content_markdown = data.get("markdown")
        content_html = data.get("html")
        metadata = data.get("metadata")
        links = data.get("links")
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")

        # Try nested data array format
        if (
            not content_markdown
            and not content_html
            and "data" in data
            and isinstance(data["data"], list)
            and len(data["data"]) > 0
        ):
            first_item = data["data"][0]
            if isinstance(first_item, dict):
                content_markdown = first_item.get("markdown")
                content_html = first_item.get("html")
                metadata = first_item.get("metadata")
                links = first_item.get("links")
                summary_text = summary_text or first_item.get("summary")
                screenshots = (
                    screenshots or first_item.get("screenshots") or first_item.get("images")
                )

        # Try nested data object format
        if not content_markdown and not content_html and isinstance(data.get("data"), dict):
            obj = data["data"]
            content_markdown = obj.get("markdown")
            content_html = obj.get("html")
            metadata = obj.get("metadata")
            links = obj.get("links")
            summary_text = summary_text or obj.get("summary")
            screenshots = screenshots or obj.get("screenshots") or obj.get("images")

        # Enrich metadata with summary and screenshots
        metadata_enriched = metadata
        if summary_text or screenshots:
            metadata_enriched = dict(metadata_enriched or {})
            if summary_text:
                metadata_enriched["summary_text"] = summary_text
            if screenshots:
                metadata_enriched["screenshots"] = screenshots

        return content_markdown, content_html, metadata_enriched, links

    @staticmethod
    def enrich_metadata(
        data: dict[str, Any],
        base_metadata: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Enrich metadata with summary and screenshots from data.

        Args:
            data: Response data that may contain summary/screenshots
            base_metadata: Base metadata dictionary to enrich

        Returns:
            Enriched metadata dictionary, or original if no enrichment needed
        """
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")
        metadata_enriched = base_metadata

        if summary_text or screenshots:
            metadata_enriched = dict(metadata_enriched or {})
            if summary_text:
                metadata_enriched["summary_text"] = summary_text
            if screenshots:
                metadata_enriched["screenshots"] = screenshots

        return metadata_enriched

    @staticmethod
    def extract_error_content(
        data: dict[str, Any],
    ) -> tuple[str | None, str | None, dict[str, Any] | None, Any, str | None, Any]:
        """Extract content from error response for partial result building.

        Similar to extract_content_fields but for error scenarios where
        we want to preserve any partial content that was returned.

        Args:
            data: Parsed response data dictionary

        Returns:
            Tuple of (markdown, html, metadata, links, summary, screenshots)
        """
        error_content_markdown = data.get("markdown")
        error_content_html = data.get("html")
        error_metadata = data.get("metadata")
        error_links = data.get("links")
        summary_text = data.get("summary")
        screenshots = data.get("screenshots") or data.get("images")

        # Try nested data array format
        if (
            not error_content_markdown
            and not error_content_html
            and "data" in data
            and isinstance(data["data"], list)
            and len(data["data"]) > 0
        ):
            first_item = data["data"][0]
            if isinstance(first_item, dict):
                error_content_markdown = first_item.get("markdown")
                error_content_html = first_item.get("html")
                error_metadata = first_item.get("metadata")
                error_links = first_item.get("links")
                summary_text = summary_text or first_item.get("summary")
                screenshots = (
                    screenshots or first_item.get("screenshots") or first_item.get("images")
                )

        # Try nested data object format
        if (
            not error_content_markdown
            and not error_content_html
            and isinstance(data.get("data"), dict)
        ):
            obj = data["data"]
            error_content_markdown = obj.get("markdown")
            error_content_html = obj.get("html")
            error_metadata = obj.get("metadata")
            error_links = obj.get("links")
            summary_text = summary_text or obj.get("summary")
            screenshots = screenshots or obj.get("screenshots") or obj.get("images")

        return (
            error_content_markdown,
            error_content_html,
            error_metadata,
            error_links,
            summary_text,
            screenshots,
        )
