"""Ratatoskr CLI exception types."""

from __future__ import annotations

import click


class RatatoskrError(click.ClickException):
    """Base error for Ratatoskr CLI."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class APIError(RatatoskrError):
    """Error from the Ratatoskr API."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")


class AuthError(RatatoskrError):
    """Authentication error."""


class ConfigError(RatatoskrError):
    """Missing or invalid configuration."""
