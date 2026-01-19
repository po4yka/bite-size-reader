"""Stateless data formatting operations."""

from __future__ import annotations

import math
from typing import Any


class DataFormatterImpl:
    """Stateless implementation of data formatting operations."""

    def format_bytes(self, size: int) -> str:
        """Convert byte count into a human-readable string."""
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{value:.1f} TB"

    def format_metric_value(self, value: Any) -> str | None:
        """Format metric values, trimming insignificant decimals and booleans."""
        if value is None:
            return None
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return str(value)
            if value.is_integer():
                return str(int(value))
            return f"{value:.2f}".rstrip("0").rstrip(".")
        return str(value).strip()

    def format_key_stats(self, key_stats: list[dict[str, Any]]) -> list[str]:
        """Render key statistics into bullet-point lines."""
        formatted: list[str] = []
        for entry in key_stats:
            if not isinstance(entry, dict):
                continue

            label = str(entry.get("label", "")).strip()
            if not label:
                continue

            value_text = self.format_metric_value(entry.get("value"))
            unit = str(entry.get("unit", "")).strip()
            source_excerpt = str(entry.get("source_excerpt", "")).strip()

            detail_parts: list[str] = []
            if value_text is not None:
                if unit:
                    detail_parts.append(f"{value_text} {unit}".strip())
                else:
                    detail_parts.append(value_text)
            elif unit:
                detail_parts.append(unit)

            if source_excerpt:
                detail_parts.append(f"Source: {source_excerpt}")

            if detail_parts:
                formatted.append(f"• {label}: " + " — ".join(detail_parts))
            else:
                formatted.append(f"• {label}")

        return formatted

    def format_readability(self, readability: Any) -> str | None:
        """Create a reader-friendly readability summary line."""
        if not isinstance(readability, dict):
            return None

        method_raw = str(readability.get("method", "")).strip()
        method_display = method_raw[:1].upper() + method_raw[1:] if method_raw else ""

        score = self.format_metric_value(readability.get("score"))
        level_raw = str(readability.get("level", "")).strip()
        level_display = level_raw[:1].upper() + level_raw[1:] if level_raw else ""

        detail_parts: list[str] = []
        if score is not None:
            detail_parts.append(f"Score: {score}")
        if level_display:
            detail_parts.append(f"Level: {level_display}")

        details = " • ".join(detail_parts)
        if method_display and details:
            return f"{method_display} • {details}"
        if method_display:
            return method_display
        return details or None

    def format_firecrawl_options(self, options: dict[str, Any] | None) -> str | None:
        """Format Firecrawl options into a display string."""
        if not isinstance(options, dict) or not options:
            return None

        parts: list[str] = []

        mobile = options.get("mobile")
        if isinstance(mobile, bool):
            parts.append("mobile=on" if mobile else "mobile=off")

        formats = options.get("formats")
        if isinstance(formats, list | tuple):
            fmt_values = [str(v).strip() for v in formats if str(v).strip()]
            if fmt_values:
                parts.append("formats=" + ", ".join(fmt_values[:5]))

        parsers = options.get("parsers")
        if isinstance(parsers, list | tuple):
            parser_values = [str(v).strip() for v in parsers if str(v).strip()]
            if parser_values:
                parts.append("parsers=" + ", ".join(parser_values[:5]))

        for key, value in options.items():
            if key in {"mobile", "formats", "parsers"}:
                continue
            if isinstance(value, bool):
                parts.append(f"{key}={'on' if value else 'off'}")
            elif isinstance(value, int | float):
                parts.append(f"{key}={value}")
            elif isinstance(value, str):
                clean = value.strip()
                if clean:
                    parts.append(f"{key}={clean}")
            elif isinstance(value, list | tuple):
                clean_values = [str(v).strip() for v in value if str(v).strip()]
                if clean_values:
                    parts.append(f"{key}=" + ", ".join(clean_values[:5]))

        if not parts:
            return None

        return "; ".join(parts)
