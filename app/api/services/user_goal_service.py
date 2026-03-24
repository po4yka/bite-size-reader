"""Service logic for reading goal endpoints."""

from __future__ import annotations

import datetime as _dt
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.api.dependencies.database import get_session_manager
from app.api.exceptions import ResourceNotFoundError
from app.api.models.responses import GoalProgressResponse, GoalResponse
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from app.api.models.requests import CreateGoalRequest
    from app.db.session import DatabaseSessionManager


def _safe_isoformat(dt_value: Any) -> str | None:
    if dt_value is None:
        return None
    if hasattr(dt_value, "isoformat") and not isinstance(dt_value, str):
        return dt_value.isoformat() + "Z"
    if isinstance(dt_value, str):
        try:
            parsed = datetime.fromisoformat(dt_value.replace("Z", "+00:00"))
            return parsed.isoformat() + "Z"
        except (ValueError, AttributeError):
            return dt_value if dt_value else None
    return None


class UserGoalService:
    """Owns goal persistence, scope validation, and progress calculations."""

    def __init__(self, session_manager: DatabaseSessionManager | None = None) -> None:
        self._db = session_manager or get_session_manager()

    async def list_goals(self, *, user_id: int) -> list[dict[str, Any]]:
        """List all goals for a user."""

        def _query() -> list[dict[str, Any]]:
            from app.db.models import UserGoal

            goals = UserGoal.select().where(UserGoal.user == user_id)
            return [self._goal_to_payload(goal, user_id=user_id) for goal in goals]

        return await self._db.async_execute(
            _query, operation_name="list_user_goals", read_only=True
        )

    async def upsert_goal(self, *, user_id: int, body: CreateGoalRequest) -> dict[str, Any]:
        """Create or update a scoped reading goal."""

        def _upsert() -> dict[str, Any]:
            from app.db.models import UserGoal

            self._validate_scope_ownership(
                user_id=user_id,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
            )
            goal, created = UserGoal.get_or_create(
                user=user_id,
                goal_type=body.goal_type,
                scope_type=body.scope_type,
                scope_id=body.scope_id,
                defaults={"id": uuid.uuid4(), "target_count": body.target_count},
            )
            if not created:
                goal.target_count = body.target_count
                goal.save()
            return self._goal_to_payload(goal, user_id=user_id)

        return await self._db.async_execute(_upsert, operation_name="upsert_user_goal")

    async def delete_global_goal(self, *, user_id: int, goal_type: str) -> None:
        """Delete a global goal by type."""

        def _delete() -> None:
            from app.db.models import UserGoal

            deleted_count = (
                UserGoal.delete()
                .where(
                    (UserGoal.user == user_id)
                    & (UserGoal.goal_type == goal_type)
                    & (UserGoal.scope_type == "global")
                )
                .execute()
            )
            if deleted_count == 0:
                raise ResourceNotFoundError("Goal", goal_type)

        await self._db.async_execute(_delete, operation_name="delete_global_user_goal")

    async def delete_goal_by_id(self, *, user_id: int, goal_id: str) -> None:
        """Delete a goal by its UUID."""

        def _delete() -> None:
            from app.db.models import UserGoal

            deleted_count = (
                UserGoal.delete()
                .where((UserGoal.user == user_id) & (UserGoal.id == goal_id))
                .execute()
            )
            if deleted_count == 0:
                raise ResourceNotFoundError("Goal", goal_id)

        await self._db.async_execute(_delete, operation_name="delete_user_goal_by_id")

    async def get_goal_progress(self, *, user_id: int) -> list[dict[str, Any]]:
        """Return progress for each goal."""

        def _build_progress() -> list[dict[str, Any]]:
            from app.db.models import UserGoal

            goals = list(UserGoal.select().where(UserGoal.user == user_id))
            if not goals:
                return []

            streak_data = self._compute_streak_data(user_id=user_id)
            now = datetime.now(UTC)
            today = now.date()
            progress_list: list[dict[str, Any]] = []

            for goal in goals:
                scope_type = getattr(goal, "scope_type", "global")
                scope_id = getattr(goal, "scope_id", None)

                if scope_type == "global":
                    current_count = self._global_goal_count(
                        goal_type=goal.goal_type, streak_data=streak_data
                    )
                else:
                    start, end = self._goal_period_bounds(goal_type=goal.goal_type, today=today)
                    current_count = self._count_summaries_in_period(
                        user_id=user_id,
                        start=start,
                        end=end,
                        scope_type=scope_type,
                        scope_id=scope_id,
                    )

                progress_list.append(
                    GoalProgressResponse(
                        goal_type=goal.goal_type,
                        target_count=goal.target_count,
                        current_count=current_count,
                        achieved=current_count >= goal.target_count,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        scope_name=self._resolve_scope_name(
                            user_id=user_id,
                            scope_type=scope_type,
                            scope_id=scope_id,
                        ),
                    ).model_dump(by_alias=True)
                )

            return progress_list

        return await self._db.async_execute(
            _build_progress,
            operation_name="get_user_goal_progress",
            read_only=True,
        )

    @staticmethod
    def _validate_scope_ownership(*, user_id: int, scope_type: str, scope_id: int | None) -> None:
        if scope_type == "tag" and scope_id is not None:
            from app.db.models import Tag

            tag = Tag.get_or_none((Tag.id == scope_id) & (Tag.user == user_id) & (~Tag.is_deleted))
            if not tag:
                raise ResourceNotFoundError("Tag", str(scope_id))
        elif scope_type == "collection" and scope_id is not None:
            from app.db.models import Collection

            collection = Collection.get_or_none(
                (Collection.id == scope_id)
                & (Collection.user == user_id)
                & (~Collection.is_deleted)
            )
            if not collection:
                raise ResourceNotFoundError("Collection", str(scope_id))

    @staticmethod
    def _resolve_scope_name(*, user_id: int, scope_type: str, scope_id: int | None) -> str | None:
        if scope_type == "tag" and scope_id is not None:
            from app.db.models import Tag

            tag = Tag.get_or_none((Tag.id == scope_id) & (Tag.user == user_id) & (~Tag.is_deleted))
            return tag.name if tag else None
        if scope_type == "collection" and scope_id is not None:
            from app.db.models import Collection

            collection = Collection.get_or_none(
                (Collection.id == scope_id)
                & (Collection.user == user_id)
                & (~Collection.is_deleted)
            )
            return collection.name if collection else None
        return None

    def _goal_to_payload(self, goal: Any, *, user_id: int) -> dict[str, Any]:
        return GoalResponse(
            id=str(goal.id),
            goal_type=goal.goal_type,
            target_count=goal.target_count,
            scope_type=goal.scope_type,
            scope_id=goal.scope_id,
            scope_name=self._resolve_scope_name(
                user_id=user_id,
                scope_type=goal.scope_type,
                scope_id=goal.scope_id,
            ),
            created_at=_safe_isoformat(goal.created_at) or "",
            updated_at=_safe_isoformat(goal.updated_at) or "",
        ).model_dump(by_alias=True)

    @staticmethod
    def _goal_period_bounds(*, goal_type: str, today: _dt.date) -> tuple[datetime, datetime]:
        if goal_type == "daily":
            start = datetime(today.year, today.month, today.day, tzinfo=UTC)
            end = start + timedelta(days=1)
            return start, end
        if goal_type == "weekly":
            start_of_week = today - timedelta(days=today.weekday())
            start = datetime(start_of_week.year, start_of_week.month, start_of_week.day, tzinfo=UTC)
            return start, start + timedelta(days=7)
        start = datetime(today.year, today.month, 1, tzinfo=UTC)
        if today.month == 12:
            end = datetime(today.year + 1, 1, 1, tzinfo=UTC)
        else:
            end = datetime(today.year, today.month + 1, 1, tzinfo=UTC)
        return start, end

    @staticmethod
    def _global_goal_count(*, goal_type: str, streak_data: dict[str, Any]) -> int:
        if goal_type == "daily":
            return int(streak_data["today_count"])
        if goal_type == "weekly":
            return int(streak_data["week_count"])
        if goal_type == "monthly":
            return int(streak_data["month_count"])
        return 0

    @staticmethod
    def _count_summaries_in_period(
        *,
        user_id: int,
        start: datetime,
        end: datetime,
        scope_type: str,
        scope_id: int | None,
    ) -> int:
        from app.db.models import CollectionItem, Request, Summary, SummaryTag

        query = (
            Summary.select()
            .join(Request, on=(Summary.request == Request.id))
            .where(
                (Request.user_id == user_id)
                & (Summary.created_at >= start)
                & (Summary.created_at < end)
                & (~Summary.is_deleted)
            )
        )
        if scope_type == "tag" and scope_id is not None:
            query = query.switch(Summary).join(SummaryTag).where(SummaryTag.tag == scope_id)
        elif scope_type == "collection" and scope_id is not None:
            query = (
                query.switch(Summary)
                .join(CollectionItem)
                .where(CollectionItem.collection == scope_id)
            )
        return query.count()

    @staticmethod
    def _compute_streak_data(*, user_id: int) -> dict[str, Any]:
        from app.db.models import Request, Summary

        now = datetime.now(UTC)
        today = now.date()
        cutoff = now - timedelta(days=365)

        rows = (
            Summary.select(Summary.created_at)
            .join(Request)
            .where(
                (Request.user_id == user_id)
                & (Summary.created_at >= cutoff)
                & (~Summary.is_deleted)
            )
            .order_by(Summary.created_at.desc())
        )

        active_dates: set[_dt.date] = set()
        today_count = 0
        start_of_week = today - timedelta(days=today.weekday())
        week_count = 0
        start_of_month = today.replace(day=1)
        month_count = 0

        for row in rows:
            created = row.created_at
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if not hasattr(created, "date"):
                continue
            created_date = created.date()
            active_dates.add(created_date)
            if created_date == today:
                today_count += 1
            if created_date >= start_of_week:
                week_count += 1
            if created_date >= start_of_month:
                month_count += 1

        if not active_dates:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "last_activity_date": None,
                "today_count": 0,
                "week_count": 0,
                "month_count": 0,
            }

        sorted_dates = sorted(active_dates, reverse=True)
        current_streak = 0
        check_date: _dt.date | None = today
        if check_date not in active_dates:
            yesterday = today - timedelta(days=1)
            check_date = yesterday if yesterday in active_dates else None

        if check_date is not None:
            while check_date in active_dates:
                current_streak += 1
                check_date -= timedelta(days=1)

        longest_streak = 0
        streak = 1
        for index in range(1, len(sorted_dates)):
            if sorted_dates[index] == sorted_dates[index - 1] - timedelta(days=1):
                streak += 1
            else:
                longest_streak = max(longest_streak, streak)
                streak = 1
        longest_streak = max(longest_streak, streak)

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "last_activity_date": sorted_dates[0].isoformat(),
            "today_count": today_count,
            "week_count": week_count,
            "month_count": month_count,
        }
