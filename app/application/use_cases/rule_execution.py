"""Rule execution engine: evaluates conditions and dispatches actions."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

import httpx
import peewee

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import (
    AutomationRule,
    Collection,
    CollectionItem,
    Request,
    RuleExecutionLog,
    Summary,
    SummaryTag,
    Tag,
)
from app.domain.services.rule_engine import MAX_EXECUTIONS_PER_MINUTE, RuleConditionEvaluator
from app.domain.services.tag_service import normalize_tag_name

logger = get_logger(__name__)

# In-memory rate limiter: {user_id: [timestamp, ...]}
_user_execution_counts: dict[int, list[float]] = {}

RULE_TIMEOUT_SECONDS = 10


async def evaluate_and_execute(
    user_id: int,
    event_type: str,
    event_data: dict[str, Any],
    processing_rule_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate all matching rules for a user event and execute actions.

    Args:
        user_id: The user whose rules to evaluate.
        event_type: Event type string (e.g., "summary.created").
        event_data: Context dict with summary/request data.
        processing_rule_ids: Set of rule IDs already in the call chain (loop detection).

    Returns:
        List of execution results [{rule_id, matched, actions_taken, error}].

    """
    if processing_rule_ids is None:
        processing_rule_ids = set()

    # -- Rate limiting ---------------------------------------------------------
    now = time.time()
    window_start = now - 60.0
    timestamps = _user_execution_counts.get(user_id, [])
    timestamps = [t for t in timestamps if t > window_start]
    _user_execution_counts[user_id] = timestamps

    if len(timestamps) >= MAX_EXECUTIONS_PER_MINUTE:
        logger.warning(
            "rule_execution_rate_limited",
            extra={"user_id": user_id, "count": len(timestamps)},
        )
        return []

    # -- Load matching rules ---------------------------------------------------
    rules = list(
        AutomationRule.select()
        .where(
            AutomationRule.user == user_id,
            AutomationRule.event_type == event_type,
            AutomationRule.enabled == True,  # noqa: E712
            AutomationRule.is_deleted == False,  # noqa: E712
        )
        .order_by(AutomationRule.priority)
    )

    if not rules:
        return []

    context = _build_context(event_data)
    summary_id: int | None = event_data.get("summary_id")
    results: list[dict[str, Any]] = []

    for rule in rules:
        # -- Loop detection ----------------------------------------------------
        if rule.id in processing_rule_ids:
            logger.warning(
                "rule_execution_loop_detected",
                extra={"rule_id": rule.id, "user_id": user_id},
            )
            continue

        start_ms = time.monotonic()
        result: dict[str, Any] = {
            "rule_id": rule.id,
            "matched": False,
            "actions_taken": [],
            "error": None,
        }

        try:
            # -- Evaluate conditions -------------------------------------------
            matched, condition_results = RuleConditionEvaluator.evaluate_conditions(
                rule.conditions_json, context, rule.match_mode
            )
            result["matched"] = matched

            actions_taken: list[dict[str, Any]] = []

            if matched:
                current_ids = processing_rule_ids | {rule.id}
                for action in rule.actions_json:
                    try:
                        action_result = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None,
                                _execute_action,
                                action,
                                summary_id,
                                user_id,
                                current_ids,
                            ),
                            timeout=RULE_TIMEOUT_SECONDS,
                        )
                        actions_taken.append(action_result)
                    except TimeoutError:
                        actions_taken.append(
                            {"type": action.get("type"), "success": False, "detail": "timeout"}
                        )
                    except Exception as exc:
                        actions_taken.append(
                            {"type": action.get("type"), "success": False, "detail": str(exc)}
                        )

                result["actions_taken"] = actions_taken

                # -- Update rule stats -----------------------------------------
                AutomationRule.update(
                    {
                        AutomationRule.run_count: AutomationRule.run_count + 1,
                        AutomationRule.last_triggered_at: datetime.now(UTC),
                    }
                ).where(AutomationRule.id == rule.id).execute()

            # -- Execution log -------------------------------------------------
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            RuleExecutionLog.create(
                rule=rule.id,
                summary=summary_id,
                event_type=event_type,
                matched=matched,
                conditions_result_json=condition_results,
                actions_taken_json=actions_taken,
                error=None,
                duration_ms=elapsed_ms,
            )

            # -- Track rate ----------------------------------------------------
            _user_execution_counts.setdefault(user_id, []).append(time.time())

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_ms) * 1000)
            error_msg = str(exc)
            result["error"] = error_msg

            logger.exception(
                "rule_execution_failed",
                extra={"rule_id": rule.id, "user_id": user_id, "error": error_msg},
            )

            RuleExecutionLog.create(
                rule=rule.id,
                summary=summary_id,
                event_type=event_type,
                matched=False,
                conditions_result_json=None,
                actions_taken_json=None,
                error=error_msg,
                duration_ms=elapsed_ms,
            )

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------


def _execute_action(
    action: dict[str, Any],
    summary_id: int | None,
    user_id: int,
    processing_rule_ids: set[int],
) -> dict[str, Any]:
    """Execute a single rule action. Returns {type, success, detail}."""
    action_type = action.get("type", "")
    params = action.get("params", {})

    handler = _ACTION_HANDLERS.get(action_type)
    if handler is None:
        return {"type": action_type, "success": False, "detail": f"unknown action: {action_type}"}

    try:
        detail = handler(params, summary_id, user_id)
        return {"type": action_type, "success": True, "detail": detail}
    except Exception as exc:
        logger.exception(
            "action_execution_failed",
            extra={"action_type": action_type, "summary_id": summary_id, "error": str(exc)},
        )
        return {"type": action_type, "success": False, "detail": str(exc)}


# ---------------------------------------------------------------------------
# Individual action implementations
# ---------------------------------------------------------------------------


def _action_add_tag(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    tag_name = params.get("tag_name", "")
    normalized = normalize_tag_name(tag_name)
    if not normalized:
        return "skipped: empty tag name"

    tag, _created = Tag.get_or_create(
        user=user_id,
        normalized_name=normalized,
        defaults={"name": tag_name.strip()},
    )

    # Skip if already attached
    exists = (
        SummaryTag.select()
        .where(SummaryTag.summary == summary_id, SummaryTag.tag == tag.id)
        .exists()
    )
    if exists:
        return f"tag '{normalized}' already attached"

    SummaryTag.create(summary=summary_id, tag=tag.id, source="rule")
    return f"tag '{normalized}' added"


def _action_remove_tag(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    tag_name = params.get("tag_name", "")
    normalized = normalize_tag_name(tag_name)
    if not normalized:
        return "skipped: empty tag name"

    try:
        tag = Tag.get(Tag.user == user_id, Tag.normalized_name == normalized)
    except Tag.DoesNotExist:
        return f"tag '{normalized}' not found"

    deleted = (
        SummaryTag.delete()
        .where(SummaryTag.summary == summary_id, SummaryTag.tag == tag.id)
        .execute()
    )
    return f"tag '{normalized}' removed" if deleted else f"tag '{normalized}' was not attached"


def _action_add_to_collection(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    collection_id = params.get("collection_id")
    if collection_id is None:
        return "skipped: no collection_id"

    # Verify collection belongs to user
    try:
        Collection.get(Collection.id == collection_id, Collection.user == user_id)
    except Collection.DoesNotExist:
        return f"collection {collection_id} not found or not owned by user"

    try:
        CollectionItem.create(collection=collection_id, summary=summary_id)
        return f"added to collection {collection_id}"
    except peewee.IntegrityError:
        return f"already in collection {collection_id}"


def _action_remove_from_collection(
    params: dict[str, Any], summary_id: int | None, user_id: int
) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    collection_id = params.get("collection_id")
    if collection_id is None:
        return "skipped: no collection_id"

    deleted = (
        CollectionItem.delete()
        .where(
            CollectionItem.collection == collection_id,
            CollectionItem.summary == summary_id,
        )
        .execute()
    )
    return f"removed from collection {collection_id}" if deleted else "not in collection"


def _action_archive(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    Summary.update({Summary.is_deleted: True, Summary.deleted_at: datetime.now(UTC)}).where(
        Summary.id == summary_id
    ).execute()
    return "archived"


def _action_set_favorite(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    if summary_id is None:
        return "skipped: no summary_id"

    value = bool(params.get("value", True))
    Summary.update({Summary.is_favorited: value}).where(Summary.id == summary_id).execute()
    return f"is_favorited set to {value}"


def _action_send_webhook(params: dict[str, Any], summary_id: int | None, user_id: int) -> str:
    url = params.get("url", "")
    if not url:
        return "skipped: no webhook url"

    payload: dict[str, Any] = {
        "event": "rule.action",
        "user_id": user_id,
        "summary_id": summary_id,
    }

    # Attach summary data if available
    if summary_id is not None:
        try:
            summary = Summary.get_by_id(summary_id)
            payload["summary"] = {
                "id": summary.id,
                "lang": summary.lang,
                "is_read": summary.is_read,
                "is_favorited": summary.is_favorited,
                "created_at": str(summary.created_at),
            }
        except Summary.DoesNotExist:
            pass

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
        return f"webhook sent (status {resp.status_code})"
    except httpx.HTTPError as exc:
        return f"webhook failed: {exc}"


# Handler registry
_ACTION_HANDLERS: dict[str, Any] = {
    "add_tag": _action_add_tag,
    "remove_tag": _action_remove_tag,
    "add_to_collection": _action_add_to_collection,
    "remove_from_collection": _action_remove_from_collection,
    "archive": _action_archive,
    "set_favorite": _action_set_favorite,
    "send_webhook": _action_send_webhook,
}


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(event_data: dict[str, Any]) -> dict[str, Any]:
    """Build evaluation context from event data.

    Loads full summary+request data if only IDs are provided.
    Returns dict with keys: url, title, tags, language, reading_time,
    source_type, content.
    """
    context: dict[str, Any] = {
        "url": event_data.get("url", ""),
        "title": event_data.get("title", ""),
        "tags": event_data.get("tags", []),
        "language": event_data.get("language", ""),
        "reading_time": event_data.get("reading_time", 0),
        "source_type": event_data.get("source_type", ""),
        "content": event_data.get("content", ""),
    }

    summary_id = event_data.get("summary_id")
    if summary_id is None:
        return context

    # Enrich from DB when we have a summary_id but missing fields
    try:
        summary = Summary.get_by_id(summary_id)
    except Summary.DoesNotExist:
        return context

    # Extract fields from json_payload
    payload = summary.json_payload or {}
    if not context["title"]:
        context["title"] = payload.get("title", "")
    if not context["language"]:
        context["language"] = summary.lang or ""
    if not context["reading_time"]:
        context["reading_time"] = payload.get("estimated_reading_time_min", 0)
    if not context["source_type"]:
        context["source_type"] = payload.get("source_type", "")
    if not context["content"]:
        context["content"] = payload.get("summary_1000", "")

    # Load URL from request
    if not context["url"]:
        try:
            request = Request.get_by_id(summary.request_id)
            context["url"] = request.normalized_url or request.input_url or ""
        except Request.DoesNotExist:
            pass

    # Load tags from DB
    if not context["tags"]:
        tag_rows = (
            SummaryTag.select(SummaryTag, Tag).join(Tag).where(SummaryTag.summary == summary_id)
        )
        context["tags"] = [row.tag.normalized_name for row in tag_rows]

    return context
