from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import uuid
from typing import Any

UTC = getattr(dt, "UTC", dt.UTC)

try:  # Optional: modern logging via loguru
    from loguru import logger as loguru_logger

    _HAS_LOGURU = True
except Exception:  # pragma: no cover - optional dependency
    loguru_logger = None
    _HAS_LOGURU = False


class EnhancedJsonFormatter(logging.Formatter):
    """Enhanced JSON formatter with better field handling and performance tracking."""

    def __init__(self, include_location: bool = True, include_process_info: bool = True):
        super().__init__()
        self.include_location = include_location
        self.include_process_info = include_process_info
        self.hostname = os.uname().nodename if hasattr(os, "uname") else "unknown"

    def format(self, record: logging.LogRecord) -> str:
        # Base fields with ISO timestamp
        base: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "hostname": self.hostname,
        }

        # Add location information if enabled
        if self.include_location:
            base.update(
                {
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "pathname": record.pathname,
                }
            )

        # Add process information if enabled
        if self.include_process_info:
            base.update(
                {
                    "process": record.process,
                    "process_name": getattr(record, "processName", "MainProcess"),
                    "thread": record.thread,
                    "thread_name": getattr(record, "threadName", "MainThread"),
                }
            )

        # Add exception information
        if record.exc_info:
            base["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        # Add stack trace if available
        if record.stack_info:
            base["stack_trace"] = record.stack_info

        # Process extra fields with better categorization
        extra_fields = {}
        performance_fields = {}
        structured_output_fields = {}

        # Standard logging fields to exclude
        standard_fields = {
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
            "getMessage",
            "message",
        }

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in standard_fields or key in base:
                continue

            # Categorize special fields
            if key in (
                "latency_ms",
                "processing_time_ms",
                "tokens_prompt",
                "tokens_completion",
                "cost_usd",
                "request_duration",
                "response_time",
            ):
                performance_fields[key] = value
            elif key in (
                "structured_output_used",
                "structured_output_mode",
                "response_format_type",
                "schema_validation",
                "json_repair_attempts",
                "fallback_mode",
            ):
                structured_output_fields[key] = value
            else:
                extra_fields[key] = value

        # Add categorized fields if they exist
        if performance_fields:
            base["performance"] = performance_fields
        if structured_output_fields:
            base["structured_output"] = structured_output_fields
        if extra_fields:
            base["extra"] = extra_fields

        # Add correlation tracking
        if hasattr(record, "correlation_id") or hasattr(record, "cid"):
            base["correlation_id"] = getattr(record, "correlation_id", None) or getattr(
                record, "cid", None
            )

        if hasattr(record, "request_id"):
            base["request_id"] = record.request_id

        if hasattr(record, "user_id"):
            base["user_id"] = record.user_id

        # Be resilient to non-JSON-serializable values
        return json.dumps(
            base, ensure_ascii=False, default=self._json_serializer, separators=(",", ":")
        )

    def _json_serializer(self, obj: Any) -> str:
        """Custom JSON serializer for non-standard types."""
        if hasattr(obj, "__dict__"):
            return f"<{obj.__class__.__name__}>"
        if hasattr(obj, "__str__"):
            return str(obj)
        return f"<non-serializable: {type(obj).__name__}>"


def setup_json_logging(
    level: str = "INFO",
    include_location: bool = True,
    include_process_info: bool = True,
    use_loguru: bool = True,
    log_file: str | None = None,
    max_file_size: str = "100 MB",
    retention: str = "30 days",
) -> None:
    """Configure enhanced JSON logging with optional file output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_location: Include file/line information in logs
        include_process_info: Include process/thread information
        use_loguru: Use loguru if available (recommended)
        log_file: Optional log file path for persistent logging
        max_file_size: Maximum size per log file (loguru format)
        retention: Log retention period (loguru format)

    """
    lvl = getattr(logging, level.upper(), logging.INFO)

    if _HAS_LOGURU and use_loguru:
        # Remove existing handlers to avoid duplicate logs
        try:
            loguru_logger.remove()
        except Exception:  # pragma: no cover
            pass

        # Enhanced loguru format with structured fields
        log_format = (
            "{"
            '"timestamp": "{time:YYYY-MM-DDTHH:mm:ss.SSSZ}", '
            '"level": "{level}", '
            '"logger": "{name}", '
            '"message": "{message}", '
            '"module": "{module}", '
            '"function": "{function}", '
            '"line": {line}, '
            '"process": {process.id}, '
            '"thread": {thread.id}'
            "{extra}"
            "}"
        )

        # Add console sink
        loguru_logger.add(
            sys.stdout,
            format=log_format,
            level=level.upper(),
            serialize=True,
            enqueue=True,  # Thread-safe logging
            backtrace=True,
            diagnose=True,
        )

        # Add file sink if specified
        if log_file:
            loguru_logger.add(
                log_file,
                format=log_format,
                level=level.upper(),
                serialize=True,
                rotation=max_file_size,
                retention=retention,
                compression="gz",
                enqueue=True,
                backtrace=True,
                diagnose=True,
            )

        # Enhanced bridge for stdlib logging
        class EnhancedInterceptHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                level_to_use: int | str
                try:
                    level_to_use = loguru_logger.level(record.levelname).name
                except Exception:
                    level_to_use = record.levelno

                # Extract extra fields
                extra = {}
                standard_fields = {
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
                    "getMessage",
                    "message",
                }

                for key, value in record.__dict__.items():
                    if key.startswith("_") or key in standard_fields:
                        continue
                    extra[key] = value

                loguru_logger.bind(**extra).opt(depth=6, exception=record.exc_info).log(
                    level_to_use, record.getMessage()
                )

        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(lvl)
        root.addHandler(EnhancedInterceptHandler())

        # Reduce noise from verbose third-party loggers
        for noisy_logger in (
            "pyrogram",
            "pyrogram.session",
            "pyrogram.session.session",
        ):
            logging.getLogger(noisy_logger).setLevel(logging.INFO)

        # Log setup completion
        loguru_logger.info(
            "Enhanced JSON logging initialized with loguru",
            setup_config={
                "level": level,
                "include_location": include_location,
                "include_process_info": include_process_info,
                "log_file": log_file,
                "max_file_size": max_file_size,
                "retention": retention,
            },
        )
        return

    # Fallback: enhanced stdlib JSON logs
    root = logging.getLogger()
    root.setLevel(lvl)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        EnhancedJsonFormatter(
            include_location=include_location, include_process_info=include_process_info
        )
    )
    root.handlers.clear()
    root.addHandler(console_handler)

    # File handler if specified
    if log_file:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=5,
        )
        file_handler.setFormatter(
            EnhancedJsonFormatter(
                include_location=include_location, include_process_info=include_process_info
            )
        )
        root.addHandler(file_handler)

    # Log setup completion
    logging.info(
        "Enhanced JSON logging initialized with stdlib",
        extra={
            "setup_config": {
                "level": level,
                "include_location": include_location,
                "include_process_info": include_process_info,
                "log_file": log_file,
            }
        },
    )

    for noisy_logger in (
        "pyrogram",
        "pyrogram.session",
        "pyrogram.session.session",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name.

    This is a convenience wrapper around logging.getLogger() that provides
    consistent logger initialization across the application.

    Args:
        name: Logger name, typically __name__ of the calling module

    Returns:
        Logger instance for the given name
    """
    return logging.getLogger(name)


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

    # Smart truncation: try to break at word boundaries
    if max_length > 20:
        truncate_at = max_length - 15  # Leave space for ellipsis
        truncated = content[:truncate_at]

        # Find last space within reasonable distance
        last_space = truncated.rfind(" ", max(0, truncate_at - 50))
        if last_space > truncate_at - 100:
            truncated = truncated[:last_space]

        return truncated + "... [truncated]"

    return content[:max_length] + "..."


# Export commonly used items
__all__ = [
    "EnhancedJsonFormatter",
    "generate_correlation_id",
    "get_logger",
    "setup_json_logging",
    "truncate_log_content",
]
