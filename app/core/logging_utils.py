from __future__ import annotations

import json
import logging
import sys
from typing import Any
import uuid


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
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
            if key not in ("args", "msg", "name", "levelno", "levelname", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process"):
                base[key] = value
        return json.dumps(base, ensure_ascii=False)


def setup_json_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # Clear existing handlers to avoid duplicates in certain runtimes
    root.handlers.clear()
    root.addHandler(handler)


def generate_correlation_id() -> str:
    """Generate a short correlation ID for tracing errors across logs and user messages."""
    return uuid.uuid4().hex[:12]
