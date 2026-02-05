from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

import orjson
from loguru import logger as loguru_logger


def _json_sink(message: Any) -> None:
    """Custom loguru sink that writes structured JSON to stdout via orjson."""
    record = message.record
    log_entry: dict[str, Any] = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
        "level": record["level"].name,
        "logger": record["name"],
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
        "process": record["process"].id,
        "thread": record["thread"].id,
    }
    # Merge extra fields (correlation_id, etc.)
    for k, v in record["extra"].items():
        if k not in log_entry:
            log_entry[k] = v
    # Include exception info when present
    if record["exception"] is not None:
        log_entry["exception"] = str(message).rstrip("\n")
    try:
        data = orjson.dumps(log_entry)
    except (TypeError, ValueError):
        # Fallback: stringify non-serializable values and retry
        for k, v in log_entry.items():
            if not isinstance(v, (str, int, float, bool, type(None))):
                log_entry[k] = repr(v)
        try:
            data = orjson.dumps(log_entry)
        except Exception:
            # Last resort: emit minimal plain-text line
            data = f'{{"level":"{record["level"].name}","message":"{record["message"]}"}}'.encode()
    sys.stdout.buffer.write(data + b"\n")
    sys.stdout.buffer.flush()


def setup_json_logging(
    level: str = "INFO",
    include_location: bool = True,
    include_process_info: bool = True,
    log_file: str | None = None,
    max_file_size: str = "100 MB",
    retention: str = "30 days",
) -> None:
    """Configure enhanced JSON logging via loguru with optional file output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        include_location: Include file/line information in logs
        include_process_info: Include process/thread information
        log_file: Optional log file path for persistent logging
        max_file_size: Maximum size per log file (loguru format)
        retention: Log retention period (loguru format)

    """
    lvl = getattr(logging, level.upper(), logging.INFO)

    # Remove existing handlers to avoid duplicate logs
    try:
        loguru_logger.remove()
    except Exception:  # pragma: no cover
        pass

    # Add console sink -- custom function builds JSON via orjson
    loguru_logger.add(
        _json_sink,
        level=level.upper(),
        enqueue=True,  # Thread-safe logging
        backtrace=True,
        diagnose=True,
    )

    # Add file sink if specified -- serialize=True alone (without a custom format
    # string) produces loguru's built-in JSON schema, which is safe and correct.
    if log_file:
        loguru_logger.add(
            log_file,
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


def log_exception(
    logger: logging.Logger,
    event: str,
    exc: BaseException,
    *,
    level: str = "error",
    **extra: Any,
) -> None:
    """Log an exception with structured context and traceback."""
    payload = {"error": str(exc), "error_type": type(exc).__name__}
    payload.update(extra)

    if level == "warning":
        logger.warning(event, exc_info=exc, extra=payload)
    elif level == "info":
        logger.info(event, exc_info=exc, extra=payload)
    else:
        logger.error(event, exc_info=exc, extra=payload)


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
    "generate_correlation_id",
    "get_logger",
    "log_exception",
    "setup_json_logging",
    "truncate_log_content",
]
