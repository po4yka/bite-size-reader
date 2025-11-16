"""
User preferences and statistics endpoints.
"""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.api.models.requests import UpdatePreferencesRequest
from app.core.logging_utils import get_logger
from app.db.models import Request as RequestModel, Summary, User

logger = get_logger(__name__)
router = APIRouter()


@router.get("/preferences")
async def get_user_preferences(user=Depends(get_current_user)):
    """Get user preferences."""
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()

    # Default preferences
    default_preferences = {
        "lang_preference": "en",
        "notification_settings": {"enabled": True, "frequency": "daily"},
        "app_settings": {"theme": "dark", "font_size": "medium"},
    }

    # Get stored preferences or use defaults
    if user_record and user_record.preferences_json:
        preferences = {**default_preferences, **user_record.preferences_json}
    else:
        preferences = default_preferences

    return {
        "success": True,
        "data": {
            "user_id": user["user_id"],
            "telegram_username": user.get("username"),
            **preferences,
        },
    }


@router.patch("/preferences")
async def update_user_preferences(
    preferences: UpdatePreferencesRequest,
    user=Depends(get_current_user),
):
    """Update user preferences."""
    from datetime import UTC, datetime

    # Get or create user record
    user_record, _created = User.get_or_create(
        telegram_user_id=user["user_id"],
        defaults={"username": user.get("username"), "is_owner": False},
    )

    # Get current preferences or start with empty dict
    current_prefs = user_record.preferences_json or {}

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
    user_record.preferences_json = current_prefs
    user_record.save()

    return {
        "success": True,
        "data": {
            "updated_fields": updated_fields,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    }


@router.get("/stats")
async def get_user_stats(user=Depends(get_current_user)):
    """Get user statistics."""
    from collections import Counter

    # Query summaries for this user only (with JOIN to filter by user_id)
    user_summaries_query = (
        Summary.select(Summary, RequestModel)
        .join(RequestModel)
        .where(RequestModel.user_id == user["user_id"])
    )

    # Get summary counts
    total_summaries = user_summaries_query.count()
    unread_count = user_summaries_query.switch(Summary).where(~Summary.is_read).count()
    read_count = user_summaries_query.switch(Summary).where(Summary.is_read).count()

    # Get reading time, favorite topics, and domains
    summaries = list(user_summaries_query)
    total_reading_time = 0
    topic_counter = Counter()
    domain_counter = Counter()

    for summary in summaries:
        json_payload = summary.json_payload or {}
        total_reading_time += json_payload.get("estimated_reading_time_min", 0)

        # Count topic tags
        topic_tags = json_payload.get("topic_tags", [])
        for tag in topic_tags:
            if tag:
                topic_counter[tag.lower()] += 1

        # Count domains (from metadata or request URL)
        metadata = json_payload.get("metadata", {})
        domain = metadata.get("domain")
        if not domain and summary.request.normalized_url:
            # Extract domain from URL
            from urllib.parse import urlparse

            try:
                parsed = urlparse(summary.request.normalized_url)
                domain = parsed.netloc
            except Exception:
                pass

        if domain:
            domain_counter[domain] += 1

    average_reading_time = total_reading_time / total_summaries if total_summaries > 0 else 0

    # Get top topics and domains
    favorite_topics = [{"tag": tag, "count": count} for tag, count in topic_counter.most_common(10)]
    favorite_domains = [
        {"domain": domain, "count": count} for domain, count in domain_counter.most_common(10)
    ]

    # Language distribution
    en_count = user_summaries_query.switch(Summary).where(Summary.lang == "en").count()
    ru_count = user_summaries_query.switch(Summary).where(Summary.lang == "ru").count()

    # Get user record and last summary timestamp
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()

    # Get most recent summary timestamp
    last_summary = (
        RequestModel.select()
        .where(RequestModel.user_id == user["user_id"])
        .order_by(RequestModel.created_at.desc())
        .first()
    )
    last_summary_at = last_summary.created_at.isoformat() + "Z" if last_summary else None

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
            "last_summary_at": last_summary_at,
        },
    }
