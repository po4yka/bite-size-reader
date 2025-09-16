from __future__ import annotations

import json
import logging
import sys
import uuid
from typing import Any

try:  # Optional: modern logging via loguru
    from loguru import logger as loguru_logger

    _HAS_LOGURU = True
except Exception:  # pragma: no cover - optional dependency
    loguru_logger = None
    _HAS_LOGURU = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in base:
                continue
            # Attach extra fields provided via logger.extra
            if key not in (
                "args",
                "msg",
                "name",
                "levelno",
                "levelname",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                base[key] = value
        # Be resilient to non-JSON-serializable extras (e.g., MagicMocks in tests)
        return json.dumps(base, ensure_ascii=False, default=str)


def setup_json_logging(level: str = "INFO") -> None:
    """Configure JSON logging.

    Uses loguru if available for a more convenient developer experience; falls back to
    stdlib logging with a JSON formatter otherwise.
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    if _HAS_LOGURU:
        # Remove existing handlers to avoid duplicate logs
        try:
            loguru_logger.remove()
        except Exception:  # pragma: no cover
            pass
        # Add JSON sink
        loguru_logger.add(sys.stdout, serialize=True, level=level.upper())

        # Bridge stdlib logging into loguru
        class InterceptHandler(logging.Handler):  # pragma: no cover - thin glue
            def emit(self, record: logging.LogRecord) -> None:
                level_to_use: int | str
                try:
                    level_to_use = loguru_logger.level(record.levelname).name
                except Exception:
                    level_to_use = record.levelno
                loguru_logger.bind().opt(depth=6, exception=record.exc_info).log(
                    level_to_use, record.getMessage()
                )

        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(lvl)
        root.addHandler(InterceptHandler())
        return

    # Fallback: stdlib JSON logs
    root = logging.getLogger()
    root.setLevel(lvl)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)


def generate_correlation_id() -> str:
    """Generate a short correlation ID for tracing errors across logs and user messages."""
    return uuid.uuid4().hex[:12]


def truncate_log_content(content: str | None, max_length: int = 1000) -> str | None:
    """Truncate large content for logging to avoid cluttering logs.

    Args:
        content: The content to potentially truncate
        max_length: Maximum length before truncation (default 1000)

    Returns:
        Truncated content with ellipsis if truncated, or original content if short enough
    """
    if not content:
        return content
    if len(content) <= max_length:
        return content
    return content[:max_length] + "... [truncated]"
