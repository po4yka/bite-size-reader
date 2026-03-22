"""Category and bulk helpers for DigestAPIService."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import peewee

from app.api.exceptions import ValidationError
from app.api.models.digest import CategoryResponse
from app.api.services._digest_api_shared import require_enabled
from app.core.channel_utils import parse_channel_input
from app.db.models import ChannelCategory, ChannelSubscription
from app.infrastructure.persistence.sqlite.digest_subscription_ops import unsubscribe_channel_atomic

if TYPE_CHECKING:
    from app.config.digest import ChannelDigestConfig


class DigestCategoryService:
    """Category CRUD and bulk operations for digest API callers."""

    _unsubscribe_atomic = staticmethod(unsubscribe_channel_atomic)

    def __init__(self, cfg: ChannelDigestConfig) -> None:
        self._cfg = cfg

    def list_categories(self, user_id: int) -> list[CategoryResponse]:
        require_enabled(self._cfg)
        categories = (
            ChannelCategory.select()
            .where(ChannelCategory.user == user_id)
            .order_by(ChannelCategory.position, ChannelCategory.name)
        )

        items: list[CategoryResponse] = []
        for category in categories:
            count = (
                ChannelSubscription.select()
                .where(
                    ChannelSubscription.category == category,
                    ChannelSubscription.is_active == True,  # noqa: E712
                )
                .count()
            )
            items.append(
                CategoryResponse(
                    id=category.id,
                    name=category.name,
                    position=category.position,
                    subscription_count=count,
                )
            )
        return items

    def create_category(self, user_id: int, name: str) -> CategoryResponse:
        require_enabled(self._cfg)
        max_pos = (
            ChannelCategory.select(peewee.fn.MAX(ChannelCategory.position))
            .where(ChannelCategory.user == user_id)
            .scalar()
        )
        position = (max_pos or 0) + 1

        try:
            category = ChannelCategory.create(user=user_id, name=name, position=position)
        except peewee.IntegrityError as exc:
            raise ValidationError(f"Category '{name}' already exists.") from exc

        return CategoryResponse(
            id=category.id,
            name=category.name,
            position=category.position,
            subscription_count=0,
        )

    def update_category(self, user_id: int, category_id: int, **fields: Any) -> CategoryResponse:
        require_enabled(self._cfg)
        category = ChannelCategory.get_or_none(
            ChannelCategory.id == category_id,
            ChannelCategory.user == user_id,
        )
        if category is None:
            raise ValidationError("Category not found.")

        changed = False
        for key in ("name", "position"):
            value = fields.get(key)
            if value is not None and getattr(category, key) != value:
                setattr(category, key, value)
                changed = True

        if changed:
            try:
                category.save()
            except peewee.IntegrityError as exc:
                raise ValidationError(f"Category '{fields.get('name')}' already exists.") from exc

        count = (
            ChannelSubscription.select()
            .where(
                ChannelSubscription.category == category,
                ChannelSubscription.is_active == True,  # noqa: E712
            )
            .count()
        )
        return CategoryResponse(
            id=category.id,
            name=category.name,
            position=category.position,
            subscription_count=count,
        )

    def delete_category(self, user_id: int, category_id: int) -> dict[str, str]:
        require_enabled(self._cfg)
        category = ChannelCategory.get_or_none(
            ChannelCategory.id == category_id,
            ChannelCategory.user == user_id,
        )
        if category is None:
            raise ValidationError("Category not found.")
        category.delete_instance()
        return {"status": "deleted"}

    def assign_category(
        self,
        user_id: int,
        subscription_id: int,
        category_id: int | None,
    ) -> dict[str, str]:
        require_enabled(self._cfg)
        subscription = ChannelSubscription.get_or_none(
            ChannelSubscription.id == subscription_id,
            ChannelSubscription.user == user_id,
        )
        if subscription is None:
            raise ValidationError("Subscription not found.")

        if category_id is not None:
            category = ChannelCategory.get_or_none(
                ChannelCategory.id == category_id,
                ChannelCategory.user == user_id,
            )
            if category is None:
                raise ValidationError("Category not found.")

        subscription.category_id = category_id
        subscription.save()
        return {"status": "updated"}

    def bulk_unsubscribe(self, user_id: int, usernames: list[str]) -> dict[str, Any]:
        require_enabled(self._cfg)
        results: list[dict[str, str]] = []
        success_count = 0
        error_count = 0

        for raw_username in usernames:
            username, error = parse_channel_input(raw_username)
            if error:
                results.append({"username": raw_username, "status": "error", "detail": error})
                error_count += 1
                continue

            status = self._unsubscribe_atomic(user_id, username)
            if status in ("not_found", "not_subscribed"):
                results.append({"username": username, "status": "error", "detail": status})
                error_count += 1
            else:
                results.append({"username": username, "status": status})
                success_count += 1

        return {
            "results": results,
            "success_count": success_count,
            "error_count": error_count,
        }

    def bulk_assign_category(
        self,
        user_id: int,
        subscription_ids: list[int],
        category_id: int | None,
    ) -> dict[str, Any]:
        require_enabled(self._cfg)
        if category_id is not None:
            category = ChannelCategory.get_or_none(
                ChannelCategory.id == category_id,
                ChannelCategory.user == user_id,
            )
            if category is None:
                raise ValidationError("Category not found.")

        results: list[dict[str, str]] = []
        success_count = 0
        error_count = 0
        for subscription_id in subscription_ids:
            subscription = ChannelSubscription.get_or_none(
                ChannelSubscription.id == subscription_id,
                ChannelSubscription.user == user_id,
            )
            if subscription is None:
                results.append(
                    {"id": str(subscription_id), "status": "error", "detail": "not_found"}
                )
                error_count += 1
                continue

            subscription.category_id = category_id
            subscription.save()
            results.append({"id": str(subscription_id), "status": "updated"})
            success_count += 1

        return {
            "results": results,
            "success_count": success_count,
            "error_count": error_count,
        }
