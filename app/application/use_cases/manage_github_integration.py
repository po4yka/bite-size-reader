"""Use case: manage a user's GitHub integration (PAT / OAuth Device Flow)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

from sqlalchemy import func, select

from app.adapters.github.exceptions import GitHubAuthError, InvalidGitHubTokenError
from app.adapters.github.github_api_client import GitHubAPIClient
from app.core.logging_utils import get_logger
from app.db.models.repository import (
    GitHubAuthMethod,
    GitHubIntegrationStatus as GitHubIntegrationStatusEnum,
    Repository,
    UserGitHubIntegration,
)
from app.security.token_crypto import encrypt_token

if TYPE_CHECKING:
    from app.db.session import Database

logger = get_logger(__name__)


@dataclass(frozen=True)
class GitHubIntegrationStatus:
    """Read-model DTO returned by get_status."""

    is_connected: bool
    auth_method: GitHubAuthMethod | None
    github_login: str | None
    github_user_id: int | None
    status: GitHubIntegrationStatusEnum | None
    last_synced_at: datetime | None
    repo_count: int


class ManageGitHubIntegrationUseCase:
    """Validate, store, query, and revoke a user's GitHub integration token."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def validate_and_store(
        self,
        token: str,
        auth_method: GitHubAuthMethod,
        user_id: int,
        *,
        correlation_id: str,
    ) -> UserGitHubIntegration:
        """Validate *token* against GitHub /user, encrypt it, and upsert the integration row.

        Raises:
            InvalidGitHubTokenError: when GitHub returns 401/403 for the token.
        """
        async with GitHubAPIClient(token) as gh:
            try:
                gh_user = await gh.get_authenticated_user()
            except GitHubAuthError as exc:
                raise InvalidGitHubTokenError(f"Token rejected by GitHub: {exc}") from exc

        encrypted = encrypt_token(token)

        async with self._db.transaction() as session:
            existing = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if existing is None:
                row = UserGitHubIntegration(
                    user_id=user_id,
                    auth_method=auth_method,
                    encrypted_token=encrypted,
                    github_login=gh_user.login,
                    github_user_id=gh_user.id,
                    status=GitHubIntegrationStatusEnum.ACTIVE,
                )
                session.add(row)
            else:
                existing.auth_method = auth_method
                existing.encrypted_token = encrypted
                existing.github_login = gh_user.login
                existing.github_user_id = gh_user.id
                existing.status = GitHubIntegrationStatusEnum.ACTIVE
                row = existing

            await session.flush()
            await session.refresh(row)

        logger.info(
            "github_integration_connected",
            extra={
                "correlation_id": correlation_id,
                "user_id": user_id,
                "auth_method": auth_method.value,
                "github_login": gh_user.login,
            },
        )
        return row

    async def get_status(self, user_id: int) -> GitHubIntegrationStatus:
        """Return current integration status DTO. is_connected=False when no row exists."""
        async with self._db.session() as session:
            row = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if row is None:
                return GitHubIntegrationStatus(
                    is_connected=False,
                    auth_method=None,
                    github_login=None,
                    github_user_id=None,
                    status=None,
                    last_synced_at=None,
                    repo_count=0,
                )

            repo_count: int = (
                await session.scalar(
                    select(func.count())
                    .select_from(Repository)
                    .where(Repository.user_id == user_id)
                )
                or 0
            )

        return GitHubIntegrationStatus(
            is_connected=True,
            auth_method=row.auth_method,
            github_login=row.github_login,
            github_user_id=row.github_user_id,
            status=row.status,
            last_synced_at=row.last_synced_at,
            repo_count=repo_count,
        )

    async def revoke(self, user_id: int) -> None:
        """Delete the integration row (user revokes on github.com themselves)."""
        async with self._db.transaction() as session:
            row = await session.scalar(
                select(UserGitHubIntegration).where(UserGitHubIntegration.user_id == user_id)
            )
            if row is not None:
                await session.delete(row)
