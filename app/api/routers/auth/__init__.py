"""
Authentication router package.

Public API: get_current_user, get_webapp_user, security, router, decode_token.
All other symbols should be imported directly from their source modules.
"""

from app.api.routers.auth.dependencies import get_current_user, get_webapp_user, security
from app.api.routers.auth.endpoints import router
from app.api.routers.auth.tokens import decode_token

__all__ = [
    "decode_token",
    "get_current_user",
    "get_webapp_user",
    "router",
    "security",
]
