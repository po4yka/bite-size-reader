"""SQLAlchemy implementation of the device repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import User, UserDevice, model_to_dict
from app.db.types import _utcnow

if TYPE_CHECKING:
    from app.db.session import Database


class SqliteDeviceRepositoryAdapter:
    """Adapter for user device operations."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_get_device_by_token(self, token: str) -> dict[str, Any] | None:
        """Get a device by its push token."""
        async with self._database.session() as session:
            device = await session.scalar(select(UserDevice).where(UserDevice.token == token))
            return model_to_dict(device)

    async def async_register_device(
        self,
        *,
        user_id: int,
        token: str,
        platform: str,
        device_id: str | None = None,
    ) -> int:
        """Register a new device for a user."""
        async with self._database.transaction() as session:
            if await session.get(User, user_id) is None:
                raise ValueError(f"User {user_id} not found")
            device = UserDevice(
                user_id=user_id,
                token=token,
                platform=platform,
                device_id=device_id,
                is_active=True,
                last_seen_at=_utcnow(),
            )
            session.add(device)
            await session.flush()
            return device.id

    async def async_update_device(
        self,
        token: str,
        *,
        user_id: int,
        platform: str,
        device_id: str | None = None,
    ) -> None:
        """Update an existing device."""
        async with self._database.transaction() as session:
            if await session.get(User, user_id) is None:
                return
            await session.execute(
                update(UserDevice)
                .where(UserDevice.token == token)
                .values(
                    user_id=user_id,
                    platform=platform,
                    device_id=device_id,
                    last_seen_at=_utcnow(),
                    is_active=True,
                )
            )

    async def async_upsert_device(
        self,
        *,
        user_id: int,
        token: str,
        platform: str,
        device_id: str | None = None,
    ) -> int:
        """Register or update a device."""
        async with self._database.transaction() as session:
            if await session.get(User, user_id) is None:
                raise ValueError(f"User {user_id} not found")
            stmt = (
                insert(UserDevice)
                .values(
                    user_id=user_id,
                    token=token,
                    platform=platform,
                    device_id=device_id,
                    is_active=True,
                    last_seen_at=_utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=[UserDevice.token],
                    set_={
                        "user_id": user_id,
                        "platform": platform,
                        "device_id": device_id,
                        "last_seen_at": _utcnow(),
                        "is_active": True,
                    },
                )
                .returning(UserDevice.id)
            )
            return int(await session.scalar(stmt) or 0)

    async def async_deactivate_device(self, token: str) -> bool:
        """Deactivate a device by token."""
        async with self._database.transaction() as session:
            result = await session.execute(
                update(UserDevice)
                .where(UserDevice.token == token)
                .values(is_active=False)
                .returning(UserDevice.id)
            )
            return result.scalar_one_or_none() is not None

    async def async_list_user_devices(
        self,
        user_id: int,
        *,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List devices for a user."""
        async with self._database.session() as session:
            stmt = select(UserDevice).where(UserDevice.user_id == user_id)
            if active_only:
                stmt = stmt.where(UserDevice.is_active.is_(True))
            rows = (await session.execute(stmt.order_by(UserDevice.id))).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def async_update_last_seen(self, token: str) -> None:
        """Update the last_seen_at timestamp for a device."""
        async with self._database.transaction() as session:
            await session.execute(
                update(UserDevice).where(UserDevice.token == token).values(last_seen_at=_utcnow())
            )
