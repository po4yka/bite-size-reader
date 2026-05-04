"""Taskiq middleware for scheduled-task observability.

ChronicFailureMiddleware ports the consecutive-failure tracking from
SchedulerService._job_consecutive_failures to the taskiq middleware layer,
preserving the existing record_scheduler_chronic_failure Prometheus metric.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from taskiq import TaskiqMiddleware

if TYPE_CHECKING:
    from taskiq.message import TaskiqMessage

from app.core.logging_utils import get_logger
from app.observability.metrics import record_scheduler_chronic_failure

logger = get_logger(__name__)

_CHRONIC_FAILURE_THRESHOLD = 3


class ChronicFailureMiddleware(TaskiqMiddleware):
    """Track consecutive task failures and emit a Prometheus metric at threshold."""

    def __init__(self) -> None:
        self._consecutive_failures: dict[str, int] = defaultdict(int)

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: Any,
    ) -> Any:
        task_name = message.task_name
        if result.is_err:
            count = self._consecutive_failures[task_name] + 1
            self._consecutive_failures[task_name] = count
            if count >= _CHRONIC_FAILURE_THRESHOLD:
                logger.error(
                    "scheduler_job_chronic_failure",
                    extra={
                        "task_name": task_name,
                        "consecutive": count,
                        "error": repr(result.error),
                    },
                )
                record_scheduler_chronic_failure(task_name)
        elif self._consecutive_failures.get(task_name, 0) > 0:
            logger.info("scheduler_job_recovered", extra={"task_name": task_name})
            self._consecutive_failures[task_name] = 0
        return result
