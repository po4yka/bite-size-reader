# ruff: noqa: TC001
"""Authentication response models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .user import PreferencesData


class TokenPair(BaseModel):
    access_token: str = Field(serialization_alias="accessToken", description="JWT access token")
    refresh_token: str | None = Field(
        default=None,
        serialization_alias="refreshToken",
        description="JWT refresh token (if available)",
    )
    expires_in: int = Field(serialization_alias="expiresIn")
    token_type: str = Field(default="Bearer", serialization_alias="tokenType")


class AuthTokensResponse(BaseModel):
    tokens: TokenPair
    session_id: int | None = Field(default=None, serialization_alias="sessionId")


class UserInfo(BaseModel):
    user_id: int = Field(serialization_alias="userId")
    username: str
    client_id: str = Field(serialization_alias="clientId")
    is_owner: bool = Field(default=False, serialization_alias="isOwner")
    created_at: str = Field(serialization_alias="createdAt")


class LoginData(BaseModel):
    tokens: TokenPair
    user: UserInfo
    preferences: PreferencesData
    session_id: int | None = Field(default=None, serialization_alias="sessionId")
