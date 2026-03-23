"""Helpers for setting httpOnly refresh-token cookies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.responses import Response

REFRESH_COOKIE_NAME = "bsr_refresh_token"
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds


def set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an httpOnly cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/v1/auth",  # Only sent to auth endpoints
    )


def clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/v1/auth",
        httponly=True,
        secure=True,
        samesite="strict",
    )
