"""
FastAPI authentication dependencies.
"""

import logging
from typing import Any

try:
    from fastapi import Depends
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except Exception:  # pragma: no cover - fallback for environments without compatible FastAPI
    logging.getLogger(__name__).debug("fastapi_security_import_failed", exc_info=True)

    class HTTPAuthorizationCredentials:  # type: ignore[no-redef]
        ...

    class HTTPBearer:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    def Depends(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc, unused-ignore]  # noqa: N802
        return None


from app.api.exceptions import AuthorizationError
from app.api.routers.auth.tokens import decode_token, validate_client_id
from app.config import Config

# HTTPBearer security scheme for JWT authentication
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current authenticated user.

    Validates JWT token and returns user data.

    Raises:
        TokenExpiredError: Access token has expired (401)
        TokenInvalidError: Token is malformed (401)
        TokenWrongTypeError: Not an access token (401)
        AuthorizationError: User not in whitelist (403)
    """
    from app.api.exceptions import TokenInvalidError

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")

    user_id = payload.get("user_id")
    if not user_id:
        raise TokenInvalidError("Missing user_id in token payload")

    # Verify user is still in whitelist when configured
    allowed_ids = Config.get_allowed_user_ids()
    if allowed_ids and user_id not in allowed_ids:
        raise AuthorizationError("User not authorized")

    # Validate client_id from token
    client_id = payload.get("client_id")
    validate_client_id(client_id)

    return {
        "user_id": user_id,
        "username": payload.get("username"),
        "client_id": client_id,
    }
