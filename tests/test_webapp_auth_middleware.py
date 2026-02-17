"""Tests for WebApp auth middleware and dual-auth in get_current_user."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.exceptions import APIException
from app.api.middleware import webapp_auth_middleware
from app.api.routers.auth.dependencies import get_current_user


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with webapp auth middleware and a protected route."""
    app = FastAPI()
    app.middleware("http")(webapp_auth_middleware)

    # Register exception handler so APIException subclasses return proper status codes
    @app.exception_handler(APIException)
    async def _api_exc_handler(request: Request, exc: APIException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})

    @app.get("/protected")
    async def protected(user=Depends(get_current_user)):
        return {"user_id": user["user_id"], "username": user.get("username")}

    return app


_FAKE_WEBAPP_USER = {
    "user_id": 123456,
    "username": "testuser",
    "first_name": "Test",
    "last_name": "User",
}

_FAKE_JWT_PAYLOAD = {
    "user_id": 789,
    "username": "jwtuser",
    "client_id": "test-client-id",
    "type": "access",
}

# Mock target: the function is lazily imported inside the middleware,
# so we patch it at the source module.
_VERIFY_TARGET = "app.api.routers.auth.webapp_auth.verify_telegram_webapp_init_data"


class TestWebAppAuthMiddleware:
    """Tests for webapp_auth_middleware + get_current_user dual-auth."""

    def test_webapp_initdata_grants_access(self):
        """Request with valid X-Telegram-Init-Data reaches protected endpoint."""
        app = _make_app()
        client = TestClient(app)

        with patch(_VERIFY_TARGET, return_value=_FAKE_WEBAPP_USER):
            resp = client.get(
                "/protected",
                headers={"X-Telegram-Init-Data": "fake_init_data"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == 123456
        assert data["username"] == "testuser"

    def test_jwt_still_works(self):
        """Request with JWT Bearer token works as before."""
        app = _make_app()
        client = TestClient(app)

        with (
            patch(
                "app.api.routers.auth.dependencies.decode_token",
                return_value=_FAKE_JWT_PAYLOAD,
            ),
            patch(
                "app.api.routers.auth.dependencies.validate_client_id",
                return_value=None,
            ),
            patch(
                "app.api.routers.auth.dependencies.Config.get_allowed_user_ids",
                return_value=set(),
            ),
        ):
            resp = client.get(
                "/protected",
                headers={"Authorization": "Bearer fake_jwt_token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == 789

    def test_jwt_takes_precedence_over_webapp(self):
        """When both JWT and initData are present, JWT wins."""
        app = _make_app()
        client = TestClient(app)

        with (
            patch(_VERIFY_TARGET, return_value=_FAKE_WEBAPP_USER),
            patch(
                "app.api.routers.auth.dependencies.decode_token",
                return_value=_FAKE_JWT_PAYLOAD,
            ),
            patch(
                "app.api.routers.auth.dependencies.validate_client_id",
                return_value=None,
            ),
            patch(
                "app.api.routers.auth.dependencies.Config.get_allowed_user_ids",
                return_value=set(),
            ),
        ):
            resp = client.get(
                "/protected",
                headers={
                    "Authorization": "Bearer fake_jwt_token",
                    "X-Telegram-Init-Data": "fake_init_data",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        # JWT user_id wins
        assert data["user_id"] == 789

    def test_no_auth_returns_401(self):
        """Request with neither JWT nor initData returns 401."""
        app = _make_app()
        client = TestClient(app)

        resp = client.get("/protected")
        assert resp.status_code == 401

    def test_invalid_initdata_falls_through_to_401(self):
        """Invalid initData doesn't crash -- falls through to 401."""
        app = _make_app()
        client = TestClient(app)

        with patch(_VERIFY_TARGET, side_effect=Exception("bad signature")):
            resp = client.get(
                "/protected",
                headers={"X-Telegram-Init-Data": "invalid_data"},
            )

        assert resp.status_code == 401
