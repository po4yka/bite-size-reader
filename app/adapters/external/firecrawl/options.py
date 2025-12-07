from __future__ import annotations

from typing import Any


class FirecrawlOptionsBuilder:
    """Build Firecrawl v2 formats and scrape options."""

    def __init__(
        self,
        *,
        max_age_seconds: int,
        remove_base64_images: bool,
        block_ads: bool,
        skip_tls_verification: bool,
        include_markdown_format: bool,
        include_html_format: bool,
        include_links_format: bool,
        include_summary_format: bool,
        include_images_format: bool,
        enable_screenshot_format: bool,
        screenshot_full_page: bool,
        screenshot_quality: int,
        screenshot_viewport_width: int | None,
        screenshot_viewport_height: int | None,
        json_prompt: str | None,
        json_schema: dict[str, Any] | None,
    ) -> None:
        self.max_age_seconds = max_age_seconds
        self.remove_base64_images = remove_base64_images
        self.block_ads = block_ads
        self.skip_tls_verification = skip_tls_verification
        self.include_markdown_format = include_markdown_format
        self.include_html_format = include_html_format
        self.include_links_format = include_links_format
        self.include_summary_format = include_summary_format
        self.include_images_format = include_images_format
        self.enable_screenshot_format = enable_screenshot_format
        self.screenshot_full_page = screenshot_full_page
        self.screenshot_quality = screenshot_quality
        self.screenshot_viewport_width = screenshot_viewport_width
        self.screenshot_viewport_height = screenshot_viewport_height
        self.json_prompt = json_prompt
        self.json_schema = json_schema

    def build_formats(self) -> list[Any]:
        formats: list[Any] = []
        if self.include_markdown_format:
            formats.append("markdown")
        if self.include_html_format:
            formats.append("html")
        if self.include_links_format:
            formats.append("links")
        if self.include_summary_format:
            formats.append("summary")
        if self.include_images_format:
            formats.append("images")

        if self.json_prompt or self.json_schema:
            json_format: dict[str, Any] = {"type": "json"}
            if self.json_prompt:
                json_format["prompt"] = self.json_prompt
            if self.json_schema:
                json_format["schema"] = self.json_schema
            formats.append(json_format)

        if self.enable_screenshot_format:
            screenshot_format: dict[str, Any] = {
                "type": "screenshot",
                "fullPage": self.screenshot_full_page,
                "quality": self.screenshot_quality,
            }
            if self.screenshot_viewport_width and self.screenshot_viewport_height:
                screenshot_format["viewport"] = {
                    "width": self.screenshot_viewport_width,
                    "height": self.screenshot_viewport_height,
                }
            formats.append(screenshot_format)

        if not formats:
            formats.append("markdown")
        return formats

    def base_options(self, *, mobile: bool, pdf: bool) -> dict[str, Any]:
        options: dict[str, Any] = {
            "mobile": mobile,
            "maxAge": self.max_age_seconds,
            "removeBase64Images": self.remove_base64_images,
            "blockAds": self.block_ads,
            "skipTlsVerification": self.skip_tls_verification,
        }
        if pdf:
            options["parsers"] = ["pdf"]
        return options

    def options_snapshot(self, *, mobile: bool, pdf: bool) -> dict[str, Any]:
        options = self.base_options(mobile=mobile, pdf=pdf)
        options["formats"] = self.build_formats()
        return options
