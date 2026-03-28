"""BSR CLI exception types."""

from __future__ import annotations

import click


class BSRError(click.ClickException):
    """Base error for BSR CLI."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class APIError(BSRError):
    """Error from the BSR API."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"[{code}] {message}")


class AuthError(BSRError):
    """Authentication error."""


class ConfigError(BSRError):
    """Missing or invalid configuration."""
