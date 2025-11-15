"""
User preferences and statistics endpoints.
"""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.api.models.requests import UpdatePreferencesRequest
from app.db.models import Summary, Request as RequestModel, User
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/preferences")
async def get_user_preferences(user=Depends(get_current_user)):
    """Get user preferences."""
    # TODO: Store preferences in database
    # For now, return mock data

    return {
        "success": True,
        "data": {
            "user_id": user["user_id"],
            "telegram_username": user.get("username"),
            "lang_preference": "en",
            "notification_settings": {"enabled": True, "frequency": "daily"},
            "app_settings": {"theme": "dark", "font_size": "medium"},
        },
    }


@router.patch("/preferences")
async def update_user_preferences(
    preferences: UpdatePreferencesRequest,
    user=Depends(get_current_user),
):
    """Update user preferences."""
    # TODO: Persist preferences to database

    updated_fields = []
    if preferences.lang_preference:
        updated_fields.append("lang_preference")
    if preferences.notification_settings:
        updated_fields.extend(
            [f"notification_settings.{k}" for k in preferences.notification_settings.keys()]
        )
    if preferences.app_settings:
        updated_fields.extend([f"app_settings.{k}" for k in preferences.app_settings.keys()])

    return {
        "success": True,
        "data": {
            "updated_fields": updated_fields,
            "updated_at": "2025-11-15T10:10:00Z",
        },
    }


@router.get("/stats")
async def get_user_stats(user=Depends(get_current_user)):
    """Get user statistics."""
    # Get summary counts
    total_summaries = Summary.select().count()
    unread_count = Summary.select().where(Summary.is_read == False).count()
    read_count = Summary.select().where(Summary.is_read == True).count()

    # Get reading time
    summaries = Summary.select()
    total_reading_time = 0
    for summary in summaries:
        json_payload = summary.json_payload or {}
        total_reading_time += json_payload.get("estimated_reading_time_min", 0)

    average_reading_time = total_reading_time / total_summaries if total_summaries > 0 else 0

    # Get favorite topics (mock)
    favorite_topics = [
        {"tag": "#blockchain", "count": 35},
        {"tag": "#crypto", "count": 28},
        {"tag": "#technology", "count": 25},
    ]

    # Get favorite domains (mock)
    favorite_domains = [
        {"domain": "medium.com", "count": 42},
        {"domain": "github.com", "count": 35},
    ]

    # Language distribution
    en_count = Summary.select().where(Summary.lang == "en").count()
    ru_count = Summary.select().where(Summary.lang == "ru").count()

    # Get user record
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()

    return {
        "success": True,
        "data": {
            "total_summaries": total_summaries,
            "unread_count": unread_count,
            "read_count": read_count,
            "total_reading_time_min": total_reading_time,
            "average_reading_time_min": round(average_reading_time, 1),
            "favorite_topics": favorite_topics,
            "favorite_domains": favorite_domains,
            "language_distribution": {"en": en_count, "ru": ru_count},
            "joined_at": user_record.created_at.isoformat() + "Z" if user_record else None,
            "last_summary_at": "2025-11-15T10:00:00Z",  # TODO: Get actual last summary
        },
    }
