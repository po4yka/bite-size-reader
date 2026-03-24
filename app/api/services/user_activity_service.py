"""User activity projections for API endpoints."""

from __future__ import annotations

import datetime as _dt
from datetime import datetime, timedelta
from typing import Any

from app.api.dependencies.database import get_summary_repository
from app.core.time_utils import UTC


class UserActivityService:
    """Computes streak and period activity summaries."""

    async def get_streak_data(self, *, user_id: int) -> dict[str, Any]:
        summary_repo = get_summary_repository()
        now = datetime.now(UTC)
        today = now.date()
        cutoff = now - timedelta(days=365)
        rows = await summary_repo.async_get_user_summary_activity_dates(user_id, cutoff)

        active_dates: set[_dt.date] = set()
        today_count = 0
        start_of_week = today - timedelta(days=today.weekday())
        week_count = 0
        start_of_month = today.replace(day=1)
        month_count = 0

        for created in rows:
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if not hasattr(created, "date"):
                continue
            date_value = created.date()
            active_dates.add(date_value)
            if date_value == today:
                today_count += 1
            if date_value >= start_of_week:
                week_count += 1
            if date_value >= start_of_month:
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
        last_activity_date = sorted_dates[0].isoformat()

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
            "last_activity_date": last_activity_date,
            "today_count": today_count,
            "week_count": week_count,
            "month_count": month_count,
        }
