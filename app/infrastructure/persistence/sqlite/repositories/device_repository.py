"""SQLite implementation of device repository.

This adapter handles UserDevice operations for push notifications.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.time_utils import UTC
from app.db.models import User, UserDevice, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


def _now() -> dt.datetime:
    """Get current UTC time."""
    return dt.datetime.now(UTC)


class SqliteDeviceRepositoryAdapter(SqliteBaseRepository):
    """Adapter for user device operations (push notifications)."""

    async def async_get_device_by_token(self, token: str) -> dict[str, Any] | None:
        """Get a device by its push token.

        Returns:
            Dict with device data or None if not found.
        """

        def _get() -> dict[str, Any] | None:
            device = UserDevice.get_or_none(UserDevice.token == token)
            return model_to_dict(device)

        return await self._execute(_get, operation_name="get_device_by_token", read_only=True)

    async def async_register_device(
        self,
        *,
        user_id: int,
        token: str,
        platform: str,
        device_id: str | None = None,
    ) -> int:
        """Register a new device for a user.

        Returns:
            The ID of the created device record.
        """

        def _create() -> int:
            user = User.get_or_none(User.telegram_user_id == user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")
            device = UserDevice.create(
                user=user,
                token=token,
                platform=platform,
                device_id=device_id,
                is_active=True,
                last_seen_at=_now(),
            )
            return device.id

        return await self._execute(_create, operation_name="register_device")

    async def async_update_device(
        self,
        token: str,
        *,
        user_id: int,
        platform: str,
        device_id: str | None = None,
    ) -> None:
        """Update an existing device.

        Args:
            token: The device token to update.
            user_id: User ID to associate.
            platform: Device platform (ios/android).
            device_id: Optional device identifier.
        """

        def _update() -> None:
            device = UserDevice.get_or_none(UserDevice.token == token)
            if not device:
                return
            user = User.get_or_none(User.telegram_user_id == user_id)
            if not user:
                return
            device.user = user
            device.platform = platform
            device.device_id = device_id
            device.last_seen_at = _now()
            device.is_active = True
            device.save()

        await self._execute(_update, operation_name="update_device")

    async def async_upsert_device(
        self,
        *,
        user_id: int,
        token: str,
        platform: str,
        device_id: str | None = None,
    ) -> int:
        """Register or update a device.

        Returns:
            The device ID.
        """

        def _upsert() -> int:
            user = User.get_or_none(User.telegram_user_id == user_id)
            if not user:
                raise ValueError(f"User {user_id} not found")

            device = UserDevice.get_or_none(UserDevice.token == token)
            if device:
                device.user = user
                device.platform = platform
                device.device_id = device_id
                device.last_seen_at = _now()
                device.is_active = True
                device.save()
                return device.id

            device = UserDevice.create(
                user=user,
                token=token,
                platform=platform,
                device_id=device_id,
                is_active=True,
                last_seen_at=_now(),
            )
            return device.id

        return await self._execute(_upsert, operation_name="upsert_device")

    async def async_deactivate_device(self, token: str) -> bool:
        """Deactivate a device by token.

        Returns:
            True if device was found and deactivated, False otherwise.
        """

        def _deactivate() -> bool:
            device = UserDevice.get_or_none(UserDevice.token == token)
            if not device:
                return False
            device.is_active = False
            device.save()
            return True

        return await self._execute(_deactivate, operation_name="deactivate_device")

    async def async_list_user_devices(
        self,
        user_id: int,
        *,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List devices for a user.

        Returns:
            List of device dicts.
        """

        def _list() -> list[dict[str, Any]]:
            query = UserDevice.select().join(User).where(User.telegram_user_id == user_id)
            if active_only:
                query = query.where(UserDevice.is_active == True)  # noqa: E712
            return [model_to_dict(d) or {} for d in query]

        return await self._execute(_list, operation_name="list_user_devices", read_only=True)

    async def async_update_last_seen(self, token: str) -> None:
        """Update the last_seen_at timestamp for a device."""

        def _update() -> None:
            UserDevice.update(last_seen_at=_now()).where(UserDevice.token == token).execute()

        await self._execute(_update, operation_name="update_device_last_seen")
