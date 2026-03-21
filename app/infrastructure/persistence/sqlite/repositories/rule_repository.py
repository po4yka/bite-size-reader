"""SQLite implementation of rule repository.

This adapter handles persistence for automation rules and execution logs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import AutomationRule, RuleExecutionLog, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

logger = get_logger(__name__)


class SqliteRuleRepositoryAdapter(SqliteBaseRepository):
    """Adapter for automation rule CRUD and execution log operations."""

    async def async_get_user_rules(
        self, user_id: int, enabled_only: bool = False
    ) -> list[dict[str, Any]]:
        """Return all non-deleted rules owned by a user."""

        def _query() -> list[dict[str, Any]]:
            clauses = (AutomationRule.user == user_id) & (
                AutomationRule.is_deleted == False  # noqa: E712
            )
            if enabled_only:
                clauses = clauses & (AutomationRule.enabled == True)  # noqa: E712
            rows = (
                AutomationRule.select()
                .where(clauses)
                .order_by(AutomationRule.priority.desc(), AutomationRule.created_at.asc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="get_user_rules", read_only=True)

    async def async_get_rule_by_id(self, rule_id: int) -> dict[str, Any] | None:
        """Return rule by ID."""

        def _query() -> dict[str, Any] | None:
            try:
                rule = AutomationRule.get_by_id(rule_id)
            except AutomationRule.DoesNotExist:
                return None
            return model_to_dict(rule)

        return await self._execute(_query, operation_name="get_rule_by_id", read_only=True)

    async def async_get_rules_by_event_type(
        self, user_id: int, event_type: str
    ) -> list[dict[str, Any]]:
        """Return enabled rules matching event type, ordered by priority."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                AutomationRule.select()
                .where(
                    (AutomationRule.user == user_id)
                    & (AutomationRule.event_type == event_type)
                    & (AutomationRule.enabled == True)  # noqa: E712
                    & (AutomationRule.is_deleted == False)  # noqa: E712
                )
                .order_by(AutomationRule.priority.desc())
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="get_rules_by_event_type", read_only=True)

    async def async_create_rule(
        self,
        user_id: int,
        name: str,
        event_type: str,
        conditions: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        match_mode: str = "all",
        priority: int = 0,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a rule and return the created record."""

        def _insert() -> dict[str, Any]:
            rule = AutomationRule.create(
                user=user_id,
                name=name,
                event_type=event_type,
                conditions_json=conditions,
                actions_json=actions,
                match_mode=match_mode,
                priority=priority,
                description=description,
            )
            d = model_to_dict(rule)
            assert d is not None
            return d

        return await self._execute(_insert, operation_name="create_rule")

    async def async_update_rule(self, rule_id: int, **fields: Any) -> dict[str, Any]:
        """Update provided fields on a rule and return the updated record."""

        def _update() -> dict[str, Any]:
            rule = AutomationRule.get_by_id(rule_id)
            field_map = {
                "name": "name",
                "description": "description",
                "enabled": "enabled",
                "event_type": "event_type",
                "match_mode": "match_mode",
                "conditions": "conditions_json",
                "actions": "actions_json",
                "priority": "priority",
            }
            for key, attr in field_map.items():
                if key in fields:
                    setattr(rule, attr, fields[key])
            rule.save()
            d = model_to_dict(rule)
            assert d is not None
            return d

        return await self._execute(_update, operation_name="update_rule")

    async def async_soft_delete_rule(self, rule_id: int) -> None:
        """Soft-delete a rule."""

        def _delete() -> None:
            AutomationRule.update(
                {
                    AutomationRule.is_deleted: True,
                    AutomationRule.deleted_at: datetime.now(UTC),
                }
            ).where(AutomationRule.id == rule_id).execute()

        await self._execute(_delete, operation_name="soft_delete_rule")

    async def async_increment_run_count(self, rule_id: int) -> None:
        """Increment run_count and set last_triggered_at to now."""

        def _increment() -> None:
            AutomationRule.update(
                {
                    AutomationRule.run_count: AutomationRule.run_count + 1,
                    AutomationRule.last_triggered_at: datetime.now(UTC),
                }
            ).where(AutomationRule.id == rule_id).execute()

        await self._execute(_increment, operation_name="increment_run_count")

    async def async_create_execution_log(
        self,
        rule_id: int,
        summary_id: int | None,
        event_type: str,
        matched: bool,
        conditions_result: list[dict[str, Any]] | None = None,
        actions_taken: list[dict[str, Any]] | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> dict[str, Any]:
        """Insert an execution log entry and return the created record."""

        def _insert() -> dict[str, Any]:
            log = RuleExecutionLog.create(
                rule=rule_id,
                summary=summary_id,
                event_type=event_type,
                matched=matched,
                conditions_result_json=conditions_result,
                actions_taken_json=actions_taken,
                error=error,
                duration_ms=duration_ms,
            )
            d = model_to_dict(log)
            assert d is not None
            return d

        return await self._execute(_insert, operation_name="create_execution_log")

    async def async_get_execution_logs(
        self, rule_id: int, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return paginated execution logs for a rule."""

        def _query() -> list[dict[str, Any]]:
            rows = (
                RuleExecutionLog.select()
                .where(RuleExecutionLog.rule == rule_id)
                .order_by(RuleExecutionLog.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                d = model_to_dict(row)
                if d is not None:
                    result.append(d)
            return result

        return await self._execute(_query, operation_name="get_execution_logs", read_only=True)
