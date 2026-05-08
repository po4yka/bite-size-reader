"""SQLAlchemy implementation of the user-credentials repository.

Backs the nickname/email + password login flow. Independent of
``ClientSecret`` (machine-client secrets) -- locking one channel must not
lock the other.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select, update

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import User, UserCredential, model_to_dict

if TYPE_CHECKING:
    from app.db.session import Database

logger = get_logger(__name__)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


class UserCredentialRepositoryAdapter:
    """Adapter for user-credential CRUD and lockout state."""

    def __init__(self, session_manager: Database) -> None:
        self._database = session_manager

    async def async_get_by_canonical(
        self, *, nickname_canonical: str | None = None, email_canonical: str | None = None
    ) -> dict[str, Any] | None:
        """Look up a credential by canonical nickname OR email.

        Exactly one of ``nickname_canonical`` / ``email_canonical`` should be
        provided; the caller chooses based on whether ``@`` was in the
        identifier. Returns None when no row matches.
        """
        if not nickname_canonical and not email_canonical:
            return None
        async with self._database.session() as session:
            stmt = select(UserCredential)
            if nickname_canonical:
                stmt = stmt.where(UserCredential.nickname_canonical == nickname_canonical)
            else:
                stmt = stmt.where(UserCredential.email_canonical == email_canonical)
            record = await session.scalar(stmt)
            return model_to_dict(record)

    async def async_get_by_user_id(self, user_id: int) -> dict[str, Any] | None:
        """Fetch the credential row for a user (one per user)."""
        async with self._database.session() as session:
            record = await session.scalar(
                select(UserCredential).where(UserCredential.user_id == user_id)
            )
            return model_to_dict(record)

    async def async_upsert(
        self,
        *,
        user_id: int,
        nickname: str,
        nickname_canonical: str,
        email: str | None,
        email_canonical: str | None,
        password_hash: str,
        pepper_version: int,
    ) -> int:
        """Create or replace the credential row for a user.

        The single-row-per-user invariant is enforced by the UNIQUE constraint
        on ``user_id``; nickname/email collisions surface as DB errors that
        callers translate to user-facing validation messages.
        """
        async with self._database.transaction() as session:
            user = await session.get(User, user_id)
            if user is None:
                msg = f"User {user_id} not found"
                raise ValueError(msg)

            existing = await session.scalar(
                select(UserCredential).where(UserCredential.user_id == user_id)
            )
            now = _utcnow()
            if existing is None:
                record = UserCredential(
                    user_id=user_id,
                    nickname=nickname,
                    nickname_canonical=nickname_canonical,
                    email=email,
                    email_canonical=email_canonical,
                    password_hash=password_hash,
                    pepper_version=pepper_version,
                    failed_attempts=0,
                    locked_until=None,
                    password_updated_at=now,
                )
                session.add(record)
                await session.flush()
                return record.id

            existing.nickname = nickname
            existing.nickname_canonical = nickname_canonical
            existing.email = email
            existing.email_canonical = email_canonical
            existing.password_hash = password_hash
            existing.pepper_version = pepper_version
            existing.failed_attempts = 0
            existing.locked_until = None
            existing.password_updated_at = now
            await session.flush()
            return existing.id

    async def async_record_failure(
        self, credential_id: int, *, max_attempts: int, lockout_minutes: int
    ) -> dict[str, Any]:
        """Atomically increment failed_attempts; lock when threshold is reached.

        Single SQL UPDATE ... RETURNING (Postgres MVCC handles concurrent
        increments safely under row-level locking) -- avoids the
        read-modify-write race that a pure-Python increment would hit.
        """
        async with self._database.transaction() as session:
            interval = func.make_interval(0, 0, 0, 0, 0, lockout_minutes, 0)
            stmt = (
                update(UserCredential)
                .where(UserCredential.id == credential_id)
                .values(
                    failed_attempts=UserCredential.failed_attempts + 1,
                    locked_until=case(
                        (
                            UserCredential.failed_attempts + 1 >= max_attempts,
                            func.now() + interval,
                        ),
                        else_=UserCredential.locked_until,
                    ),
                )
                .returning(UserCredential)
            )
            result = await session.scalars(stmt)
            record = result.one_or_none()
            return model_to_dict(record) or {}

    async def async_reset_failure(self, credential_id: int) -> None:
        """Reset failed_attempts and lockout after a successful login."""
        async with self._database.transaction() as session:
            await session.execute(
                update(UserCredential)
                .where(UserCredential.id == credential_id)
                .values(failed_attempts=0, locked_until=None)
            )

    async def async_touch_last_login(
        self, credential_id: int, ts: dt.datetime | None = None
    ) -> None:
        """Update last_login_at after a successful login."""
        async with self._database.transaction() as session:
            await session.execute(
                update(UserCredential)
                .where(UserCredential.id == credential_id)
                .values(last_login_at=ts or _utcnow())
            )

    async def async_update_password_hash(
        self, credential_id: int, *, password_hash: str, pepper_version: int
    ) -> None:
        """Replace the stored hash (e.g., opportunistic rehash on argon2 cost upgrade)."""
        async with self._database.transaction() as session:
            await session.execute(
                update(UserCredential)
                .where(UserCredential.id == credential_id)
                .values(
                    password_hash=password_hash,
                    pepper_version=pepper_version,
                    password_updated_at=_utcnow(),
                )
            )
