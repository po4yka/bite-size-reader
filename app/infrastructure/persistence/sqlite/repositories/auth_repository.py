"""SQLite implementation of auth repository.

This adapter handles RefreshToken and ClientSecret operations.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.time_utils import UTC
from app.db.models import ClientSecret, RefreshToken, User, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


def _utcnow_naive() -> dt.datetime:
    """Get current UTC time without timezone info (for SQLite compat)."""
    return dt.datetime.now(UTC).replace(tzinfo=None)


class SqliteAuthRepositoryAdapter(SqliteBaseRepository):
    """Adapter for authentication-related operations (RefreshToken, ClientSecret)."""

    # -------------------------------------------------------------------------
    # RefreshToken Operations
    # -------------------------------------------------------------------------

    async def async_create_refresh_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        client_id: str | None,
        device_info: str | None,
        ip_address: str | None,
        expires_at: dt.datetime,
    ) -> int:
        """Create a new refresh token record.

        Returns:
            The ID of the created refresh token record.
        """

        def _create() -> int:
            record = RefreshToken.create(
                user=user_id,
                token_hash=token_hash,
                client_id=client_id,
                device_info=device_info,
                ip_address=ip_address,
                expires_at=expires_at,
                is_revoked=False,
            )
            return record.id

        return await self._execute(_create, operation_name="create_refresh_token")

    async def async_get_refresh_token_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        """Get a refresh token by its hash.

        Returns:
            Dict with token data or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            record = RefreshToken.get_or_none(RefreshToken.token_hash == token_hash)
            return model_to_dict(record)

        return await self._execute(_get, operation_name="get_refresh_token_by_hash", read_only=True)

    async def async_revoke_refresh_token(self, token_hash: str) -> bool:
        """Revoke a refresh token by hash.

        Returns:
            True if token was found and revoked, False otherwise.
        """

        def _revoke() -> bool:
            record = RefreshToken.get_or_none(RefreshToken.token_hash == token_hash)
            if not record:
                return False
            record.is_revoked = True
            record.save()
            return True

        return await self._execute(_revoke, operation_name="revoke_refresh_token")

    async def async_update_refresh_token_last_used(self, token_id: int) -> None:
        """Update the last_used_at timestamp for a refresh token."""

        def _update() -> None:
            RefreshToken.update(last_used_at=dt.datetime.now(UTC)).where(
                RefreshToken.id == token_id
            ).execute()

        await self._execute(_update, operation_name="update_refresh_token_last_used")

    async def async_list_active_sessions(
        self, user_id: int, now: dt.datetime
    ) -> list[dict[str, Any]]:
        """List active (non-revoked, non-expired) sessions for a user.

        Returns:
            List of session dicts sorted by last_used_at desc.
        """

        def _list() -> list[dict[str, Any]]:
            sessions = (
                RefreshToken.select()
                .where(
                    (RefreshToken.user == user_id)
                    & (~RefreshToken.is_revoked)
                    & (RefreshToken.expires_at > now)
                )
                .order_by(RefreshToken.last_used_at.desc())
            )
            return [model_to_dict(s) or {} for s in sessions]

        return await self._execute(_list, operation_name="list_active_sessions", read_only=True)

    # -------------------------------------------------------------------------
    # ClientSecret Operations
    # -------------------------------------------------------------------------

    async def async_get_client_secret(self, user_id: int, client_id: str) -> dict[str, Any] | None:
        """Get the most recent client secret for a user/client pair.

        Returns:
            Dict with secret data or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            user = User.select().where(User.telegram_user_id == user_id).first()
            if not user:
                return None
            record = (
                ClientSecret.select()
                .where((ClientSecret.user == user) & (ClientSecret.client_id == client_id))
                .order_by(ClientSecret.created_at.desc())
                .first()
            )
            return model_to_dict(record)

        return await self._execute(_get, operation_name="get_client_secret", read_only=True)

    async def async_get_client_secret_by_id(self, key_id: int) -> dict[str, Any] | None:
        """Get a client secret by ID.

        Returns:
            Dict with secret data or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            record = ClientSecret.select().where(ClientSecret.id == key_id).first()
            return model_to_dict(record)

        return await self._execute(_get, operation_name="get_client_secret_by_id", read_only=True)

    async def async_create_client_secret(
        self,
        *,
        user_id: int,
        client_id: str,
        secret_hash: str,
        secret_salt: str,
        status: str = "active",
        label: str | None = None,
        description: str | None = None,
        expires_at: dt.datetime | None = None,
    ) -> int:
        """Create a new client secret.

        Returns:
            The ID of the created secret record.
        """

        def _create() -> int:
            user = User.select().where(User.telegram_user_id == user_id).first()
            if not user:
                raise ValueError(f"User {user_id} not found")
            record = ClientSecret.create(
                user=user,
                client_id=client_id,
                secret_hash=secret_hash,
                secret_salt=secret_salt,
                status=status,
                label=label,
                description=description,
                expires_at=expires_at,
                failed_attempts=0,
                locked_until=None,
            )
            return record.id

        return await self._execute(_create, operation_name="create_client_secret")

    async def async_update_client_secret(
        self,
        key_id: int,
        **fields: Any,
    ) -> None:
        """Update a client secret by ID."""

        def _update() -> None:
            record = ClientSecret.select().where(ClientSecret.id == key_id).first()
            if not record:
                return
            for key, value in fields.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            record.save()

        await self._execute(_update, operation_name="update_client_secret")

    async def async_revoke_active_secrets(self, user_id: int, client_id: str) -> int:
        """Revoke all active secrets for a user/client pair.

        Returns:
            Number of secrets revoked.
        """

        def _revoke() -> int:
            user = User.select().where(User.telegram_user_id == user_id).first()
            if not user:
                return 0
            count = 0
            active = ClientSecret.select().where(
                (ClientSecret.user == user)
                & (ClientSecret.client_id == client_id)
                & (ClientSecret.status == "active")
            )
            for record in active:
                record.status = "revoked"
                record.failed_attempts = 0
                record.locked_until = None
                record.save()
                count += 1
            return count

        return await self._execute(_revoke, operation_name="revoke_active_secrets")

    async def async_list_client_secrets(
        self,
        *,
        user_id: int | None = None,
        client_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List client secrets with optional filters.

        Returns:
            List of secret dicts (without hash/salt).
        """

        def _list() -> list[dict[str, Any]]:
            query = ClientSecret.select()
            if user_id is not None:
                query = query.join(User).where(User.telegram_user_id == user_id)
            if client_id:
                query = query.where(ClientSecret.client_id == client_id)
            if status:
                query = query.where(ClientSecret.status == status)
            return [model_to_dict(rec) or {} for rec in query]

        return await self._execute(_list, operation_name="list_client_secrets", read_only=True)

    async def async_increment_failed_attempts(
        self, key_id: int, max_attempts: int, lockout_minutes: int
    ) -> dict[str, Any]:
        """Increment failed attempts and potentially lock the secret.

        Returns:
            Updated secret data dict.
        """

        def _increment() -> dict[str, Any]:
            record = ClientSecret.select().where(ClientSecret.id == key_id).first()
            if not record:
                return {}
            record.failed_attempts = (record.failed_attempts or 0) + 1
            if record.failed_attempts >= max_attempts:
                record.status = "locked"
                record.locked_until = _utcnow_naive() + dt.timedelta(minutes=lockout_minutes)
            record.save()
            return model_to_dict(record) or {}

        return await self._execute(_increment, operation_name="increment_failed_attempts")

    async def async_reset_failed_attempts(self, key_id: int) -> None:
        """Reset failed attempts and unlock a secret."""

        def _reset() -> None:
            record = ClientSecret.select().where(ClientSecret.id == key_id).first()
            if not record:
                return
            record.failed_attempts = 0
            record.locked_until = None
            record.save()

        await self._execute(_reset, operation_name="reset_failed_attempts")
