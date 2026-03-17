"""
User preferences, statistics, goals, and streaks endpoints.
"""

import datetime as _dt
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

from fastapi import APIRouter, Depends

from app.api.dependencies.database import get_summary_repository, get_user_repository
from app.api.models.requests import CreateGoalRequest, UpdatePreferencesRequest
from app.api.models.responses import (
    GoalProgressResponse,
    GoalResponse,
    PreferencesData,
    PreferencesUpdateResult,
    StreakResponse,
    UserStatsData,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.application.services.topic_search_utils import ensure_mapping
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

logger = get_logger(__name__)
router = APIRouter()


def safe_isoformat(dt_value: Any) -> str | None:
    """Safely convert datetime-ish values to ISO 8601 Z form.

    Handles:
    - datetime objects -> ISO string with Z suffix
    - ISO strings -> normalized with Z suffix
    - None/invalid -> None
    """
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


@router.get("/preferences")
async def get_user_preferences(user: dict[str, Any] = Depends(get_current_user)):
    """Get user preferences."""
    user_repo = get_user_repository()
    user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])

    # Default preferences
    default_preferences: dict[str, Any] = {
        "lang_preference": "en",
        "notification_settings": {"enabled": True, "frequency": "daily"},
        "app_settings": {"theme": "dark", "font_size": "medium"},
    }

    # Build a normalized preference object with safe defaults.
    preferences: dict[str, Any] = {
        "lang_preference": default_preferences["lang_preference"],
        "notification_settings": dict(default_preferences["notification_settings"]),
        "app_settings": dict(default_preferences["app_settings"]),
    }
    stored_preferences = user_record.get("preferences_json") if user_record else None
    if isinstance(stored_preferences, dict):
        lang_preference = stored_preferences.get("lang_preference")
        if isinstance(lang_preference, str) and lang_preference:
            preferences["lang_preference"] = lang_preference

        notification_settings = stored_preferences.get("notification_settings")
        if isinstance(notification_settings, dict):
            preferences["notification_settings"].update(notification_settings)

        app_settings = stored_preferences.get("app_settings")
        if isinstance(app_settings, dict):
            preferences["app_settings"].update(app_settings)

    return success_response(
        PreferencesData(
            user_id=user["user_id"],
            telegram_username=user.get("username"),
            lang_preference=preferences.get("lang_preference"),
            notification_settings=preferences.get("notification_settings"),
            app_settings=preferences.get("app_settings"),
        )
    )


@router.patch("/preferences")
async def update_user_preferences(
    preferences: UpdatePreferencesRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Update user preferences."""
    user_repo = get_user_repository()

    # Get or create user record
    user_record, _created = await user_repo.async_get_or_create_user(
        user["user_id"],
        username=user.get("username"),
        is_owner=False,
    )

    # Get current preferences or start with empty dict
    current_prefs = user_record.get("preferences_json") or {}

    # Update preferences
    updated_fields = []
    if preferences.lang_preference:
        current_prefs["lang_preference"] = preferences.lang_preference
        updated_fields.append("lang_preference")

    if preferences.notification_settings:
        if "notification_settings" not in current_prefs:
            current_prefs["notification_settings"] = {}
        current_prefs["notification_settings"].update(preferences.notification_settings)
        updated_fields.extend(
            [f"notification_settings.{k}" for k in preferences.notification_settings]
        )

    if preferences.app_settings:
        if "app_settings" not in current_prefs:
            current_prefs["app_settings"] = {}
        current_prefs["app_settings"].update(preferences.app_settings)
        updated_fields.extend([f"app_settings.{k}" for k in preferences.app_settings])

    # Save to database
    await user_repo.async_update_user_preferences(user["user_id"], current_prefs)

    return success_response(
        PreferencesUpdateResult(
            updated_fields=updated_fields,
            updated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    )


@router.get("/stats")
async def get_user_stats(user: dict[str, Any] = Depends(get_current_user)):
    """Get user statistics."""
    from collections import Counter
    from urllib.parse import urlparse

    user_repo = get_user_repository()
    summary_repo = get_summary_repository()

    # Get user summaries with pagination (using a large limit for stats)
    summaries_list, total_summaries, unread_count = await summary_repo.async_get_user_summaries(
        user_id=user["user_id"],
        limit=10000,  # Large limit for stats
        offset=0,
    )

    read_count = total_summaries - unread_count

    # Calculate reading time, favorite topics, and domains
    total_reading_time = 0
    topic_counter: Counter = Counter()
    domain_counter: Counter = Counter()
    en_count = 0
    ru_count = 0

    for summary in summaries_list:
        json_payload = ensure_mapping(summary.get("json_payload"))
        total_reading_time += json_payload.get("estimated_reading_time_min", 0) or 0

        # Count topic tags
        topic_tags = json_payload.get("topic_tags", [])
        if isinstance(topic_tags, list):
            for tag in topic_tags:
                if tag and isinstance(tag, str):
                    topic_counter[tag.lower()] += 1

        # Count domains (from metadata or request URL)
        metadata = ensure_mapping(json_payload.get("metadata"))
        domain = metadata.get("domain")

        # Try to get domain from request data if available
        request_data = summary.get("request") or {}
        if isinstance(request_data, dict):
            normalized_url = request_data.get("normalized_url")
            if not domain and normalized_url:
                try:
                    parsed = urlparse(normalized_url)
                    domain = parsed.netloc
                except ValueError:
                    domain = ""
                    logger.warning("url_domain_parse_failed", exc_info=True)

        if domain:
            domain_counter[domain] += 1

        # Language distribution
        lang = summary.get("lang", "")
        if lang == "en":
            en_count += 1
        elif lang == "ru":
            ru_count += 1

    average_reading_time = total_reading_time / total_summaries if total_summaries > 0 else 0

    # Get top topics and domains
    favorite_topics = [
        {"topic": tag, "count": count} for tag, count in topic_counter.most_common(10)
    ]
    favorite_domains = [
        {"domain": domain, "count": count} for domain, count in domain_counter.most_common(10)
    ]

    # Get user record
    user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])

    # Get most recent summary timestamp from summaries_list
    last_summary_at = None
    if summaries_list:
        # Summaries are sorted by created_at desc
        first_summary = summaries_list[0]
        request_data = first_summary.get("request") or {}
        if isinstance(request_data, dict):
            last_summary_at = safe_isoformat(request_data.get("created_at"))

    return success_response(
        UserStatsData(
            total_summaries=total_summaries,
            unread_count=unread_count,
            read_count=read_count,
            total_reading_time_min=total_reading_time,
            average_reading_time_min=round(average_reading_time, 1),
            favorite_topics=favorite_topics,
            favorite_domains=favorite_domains,
            language_distribution={"en": en_count, "ru": ru_count},
            joined_at=safe_isoformat(user_record.get("created_at")) if user_record else None,
            last_summary_at=last_summary_at,
        )
    )


# ---------------------------------------------------------------------------
# Goals CRUD
# ---------------------------------------------------------------------------


@router.get("/goals")
def list_goals(user: dict[str, Any] = Depends(get_current_user)):
    """List all reading goals for the current user."""
    from app.db.models import UserGoal

    goals: Sequence[UserGoal] = list(UserGoal.select().where(UserGoal.user == user["user_id"]))
    return success_response(
        {
            "goals": [
                GoalResponse(
                    goal_type=g.goal_type,
                    target_count=g.target_count,
                    created_at=safe_isoformat(g.created_at) or "",
                    updated_at=safe_isoformat(g.updated_at) or "",
                ).model_dump(by_alias=True)
                for g in goals
            ],
        }
    )


@router.post("/goals")
def upsert_goal(
    body: CreateGoalRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Create or update a reading goal (one per goal_type per user)."""
    from app.db.models import UserGoal

    goal, created = UserGoal.get_or_create(
        user=user["user_id"],
        goal_type=body.goal_type,
        defaults={
            "id": uuid.uuid4(),
            "target_count": body.target_count,
        },
    )

    if not created:
        goal.target_count = body.target_count
        goal.save()

    return success_response(
        GoalResponse(
            goal_type=goal.goal_type,
            target_count=goal.target_count,
            created_at=safe_isoformat(goal.created_at) or "",
            updated_at=safe_isoformat(goal.updated_at) or "",
        )
    )


@router.delete("/goals/{goal_type}")
def delete_goal(
    goal_type: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Remove a reading goal."""
    from app.db.models import UserGoal

    deleted_count = (
        UserGoal.delete()
        .where((UserGoal.user == user["user_id"]) & (UserGoal.goal_type == goal_type))
        .execute()
    )
    if deleted_count == 0:
        from app.api.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("Goal", goal_type)

    return success_response({"deleted": True})


# ---------------------------------------------------------------------------
# Streak
# ---------------------------------------------------------------------------


def _compute_streak_data(
    user_id: int,
) -> dict[str, Any]:
    """Compute streak and period counts from summary creation dates.

    Approach:
    - Query distinct dates (UTC) of summaries for the user over the last 365
      days, ordered descending.
    - Walk backwards from today/yesterday to count the current consecutive
      streak and track the longest streak overall.
    - Also compute today / this-week / this-month counts for goal progress.
    """
    from app.db.models import Request, Summary

    now = datetime.now(UTC)
    today = now.date()
    cutoff = now - timedelta(days=365)

    # Fetch created_at timestamps for the user's non-deleted summaries in the
    # last 365 days, ordered descending.
    rows = (
        Summary.select(Summary.created_at)
        .join(Request)
        .where(
            (Request.user_id == user_id) & (Summary.created_at >= cutoff) & (~Summary.is_deleted)
        )
        .order_by(Summary.created_at.desc())
    )

    # Build set of unique active dates + period counters
    active_dates: set[_dt.date] = set()
    today_count = 0
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    week_count = 0
    start_of_month = today.replace(day=1)
    month_count = 0

    for row in rows:
        created = row.created_at
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if not hasattr(created, "date"):
            continue
        d = created.date()
        active_dates.add(d)
        if d == today:
            today_count += 1
        if d >= start_of_week:
            week_count += 1
        if d >= start_of_month:
            month_count += 1

    last_activity_date: str | None = None

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

    # Current streak: consecutive days ending today or yesterday
    current_streak = 0
    check_date: _dt.date | None = today
    # Allow starting from yesterday if today has no activity yet
    if check_date not in active_dates:
        yesterday = today - timedelta(days=1)
        check_date = yesterday if yesterday in active_dates else None

    if check_date is not None:
        while check_date in active_dates:
            current_streak += 1
            check_date -= timedelta(days=1)

    # Longest streak: walk through all sorted dates
    longest_streak = 0
    streak = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] == sorted_dates[i - 1] - timedelta(days=1):
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


@router.get("/streak")
def get_streak(user: dict[str, Any] = Depends(get_current_user)):
    """Compute and return the user's reading streak data."""
    data = _compute_streak_data(user["user_id"])
    return success_response(
        StreakResponse(
            current_streak=data["current_streak"],
            longest_streak=data["longest_streak"],
            last_activity_date=data["last_activity_date"],
            today_count=data["today_count"],
            week_count=data["week_count"],
            month_count=data["month_count"],
        )
    )


# ---------------------------------------------------------------------------
# Goal progress
# ---------------------------------------------------------------------------


@router.get("/goals/progress")
def get_goal_progress(user: dict[str, Any] = Depends(get_current_user)):
    """Return each goal with current progress."""
    from app.db.models import UserGoal

    goals: Sequence[UserGoal] = list(UserGoal.select().where(UserGoal.user == user["user_id"]))
    if not goals:
        return success_response({"progress": []})

    streak_data = _compute_streak_data(user["user_id"])

    progress_list: list[dict[str, Any]] = []
    for g in goals:
        if g.goal_type == "daily":
            current = streak_data["today_count"]
        elif g.goal_type == "weekly":
            current = streak_data["week_count"]
        elif g.goal_type == "monthly":
            current = streak_data["month_count"]
        else:
            current = 0

        progress_list.append(
            GoalProgressResponse(
                goal_type=g.goal_type,
                target_count=g.target_count,
                current_count=current,
                achieved=current >= g.target_count,
            ).model_dump(by_alias=True)
        )

    return success_response({"progress": progress_list})
