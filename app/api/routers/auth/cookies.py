"""Helpers for setting httpOnly refresh-token cookies."""

from __future__ import annotations

from starlette.responses import Response  # noqa: TC002 - needed at runtime

REFRESH_COOKIE_NAME = "ratatoskr_refresh_token"
REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds


def set_refresh_cookie(
    response: Response, token: str, *, max_age: int | None = REFRESH_COOKIE_MAX_AGE
) -> None:
    """Set the refresh token as an httpOnly cookie.

    Args:
        response: Starlette response to mutate.
        token: Refresh-token JWT.
        max_age: Cookie lifetime in seconds. Pass None to issue a session
            cookie (no Max-Age/Expires) -- the browser drops it on close.
            This is the credentials-login Remember Me=False mode.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
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
