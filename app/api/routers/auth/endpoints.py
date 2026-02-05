"""
Authentication API endpoints.

This module aggregates focused auth sub-routers into a single router exported
by `app.api.routers.auth` for backward compatibility.
"""

from __future__ import annotations

from app.api.routers.auth._fastapi import APIRouter

from . import (
    endpoints_me,
    endpoints_oauth,
    endpoints_secret_keys,
    endpoints_sessions,
    endpoints_telegram,
)

router = APIRouter()

# Aggregate routers (route paths are defined in each sub-router)
router.include_router(endpoints_telegram.router)
router.include_router(endpoints_secret_keys.router)
router.include_router(endpoints_oauth.router)
router.include_router(endpoints_me.router)
router.include_router(endpoints_sessions.router)

# Re-export handlers for tests/backward-compat (tests call these functions directly)
telegram_login = endpoints_telegram.telegram_login
get_telegram_link_status = endpoints_telegram.get_telegram_link_status
begin_telegram_link = endpoints_telegram.begin_telegram_link
complete_telegram_link = endpoints_telegram.complete_telegram_link
unlink_telegram = endpoints_telegram.unlink_telegram

secret_login = endpoints_secret_keys.secret_login
create_secret_key = endpoints_secret_keys.create_secret_key
rotate_secret_key = endpoints_secret_keys.rotate_secret_key
revoke_secret_key = endpoints_secret_keys.revoke_secret_key
list_secret_keys = endpoints_secret_keys.list_secret_keys

apple_login = endpoints_oauth.apple_login
google_login = endpoints_oauth.google_login

get_current_user_info = endpoints_me.get_current_user_info
delete_account = endpoints_me.delete_account

refresh_access_token = endpoints_sessions.refresh_access_token
logout = endpoints_sessions.logout
list_sessions = endpoints_sessions.list_sessions
