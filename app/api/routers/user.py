"""
User preferences and statistics endpoints.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from app.api.models.requests import UpdatePreferencesRequest
from app.api.models.responses import (
    PreferencesData,
    PreferencesUpdateResult,
    UserStatsData,
    success_response,
)
from app.api.routers.auth import get_current_user
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)
from app.services.topic_search_utils import ensure_mapping

logger = get_logger(__name__)
router = APIRouter()


def _safe_isoformat(dt_value: Any) -> str | None:
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
async def get_user_preferences(user=Depends(get_current_user)):
    """Get user preferences."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])

    # Default preferences
    default_preferences = {
        "lang_preference": "en",
        "notification_settings": {"enabled": True, "frequency": "daily"},
        "app_settings": {"theme": "dark", "font_size": "medium"},
    }

    # Get stored preferences or use defaults
    if user_record and user_record.get("preferences_json"):
        preferences = {**default_preferences, **user_record["preferences_json"]}
    else:
        preferences = default_preferences

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
    user=Depends(get_current_user),
):
    """Update user preferences."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)

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
async def get_user_stats(user=Depends(get_current_user)):
    """Get user statistics."""
    from collections import Counter
    from urllib.parse import urlparse

    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    summary_repo = SqliteSummaryRepositoryAdapter(database_proxy)

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
                except Exception:
                    logger.debug("url_domain_parse_failed", exc_info=True)

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
            last_summary_at = _safe_isoformat(request_data.get("created_at"))

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
            joined_at=_safe_isoformat(user_record.get("created_at")) if user_record else None,
            last_summary_at=last_summary_at,
        )
    )
