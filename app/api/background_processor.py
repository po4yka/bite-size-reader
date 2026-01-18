"""Background request processor for Mobile API with DI, Redis locks, and retries."""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.adapters.content.url_processor import URLProcessor, _get_system_prompt
from app.config import AppConfig, load_config
from app.core.lang import choose_language, detect_language
from app.core.logging_utils import get_logger
from app.core.url_utils import normalize_url
from app.db.session import DatabaseSessionManager
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.redis import get_redis, redis_key

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int
    base_delay_ms: int
    max_delay_ms: int
    jitter_ratio: float


@dataclass
class LockHandle:
    source: str
    key: str
    token: str | None
    local_lock: asyncio.Lock | None


class StageError(Exception):
    """Wrap a failure with stage context."""

    def __init__(self, stage: str, exc: Exception):
        super().__init__(str(exc))
        self.stage = stage
        self.original = exc


class BackgroundProcessor:
    """Process background requests with idempotent locking and retries."""

    def __init__(
        self,
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        redis: Any | None,
        semaphore: asyncio.Semaphore,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.url_processor = url_processor
        self.redis = redis
        self._sem = semaphore
        self._audit = audit_func
        self._local_locks: dict[int, asyncio.Lock] = {}
        self._lock_enabled = cfg.background.redis_lock_enabled
        self._lock_required = cfg.background.redis_lock_required
        self._lock_ttl_ms = cfg.background.lock_ttl_ms
        self._lock_skip_on_held = cfg.background.lock_skip_on_held
        self._retry = RetryPolicy(
            attempts=cfg.background.retry_attempts,
            base_delay_ms=cfg.background.retry_base_delay_ms,
            max_delay_ms=cfg.background.retry_max_delay_ms,
            jitter_ratio=cfg.background.retry_jitter_ratio,
        )

    async def process(
        self,
        request_id: int,
        *,
        correlation_id: str | None = None,
        db_path: str | None = None,
    ) -> None:
        """Process a request by id."""
        processor_db, processor = self._maybe_override_db(db_path)
        request: dict[str, Any] | None = None

        lock_handle = await self._acquire_lock(request_id, correlation_id)
        if lock_handle is None:
            return

        try:
            repo = (
                self.request_repo
                if processor_db == self.db
                else SqliteRequestRepositoryAdapter(processor_db)
            )
            request = await repo.async_get_request_by_id(request_id)
            if not request:
                logger.error(
                    "bg_request_not_found",
                    extra={"request_id": request_id, "correlation_id": correlation_id},
                )
                return

            if await self._has_existing_summary(processor_db, request_id):
                logger.info(
                    "bg_request_already_summarized",
                    extra={
                        "request_id": request_id,
                        "correlation_id": request.get("correlation_id") or correlation_id,
                    },
                )
                await self._publish_update(
                    request_id, "COMPLETED", "DONE", "Already summarized", 1.0
                )
                return

            cid = request.get("correlation_id") or correlation_id or f"bg-proc-{request_id}"
            await self._mark_status(processor_db, request_id, "processing", cid)
            await self._publish_update(
                request_id, "PROCESSING", "QUEUED", "Processing started", 0.0
            )

            logger.info(
                "bg_processing_start",
                extra={
                    "correlation_id": cid,
                    "request_id": request_id,
                    "type": request.get("type"),
                    "url": request.get("input_url"),
                },
            )

            if request.get("type") == "url":
                await self._process_url_type(request_id, request, processor_db, processor, cid)
            elif request.get("type") == "forward":
                await self._process_forward_type(request_id, request, processor_db, processor, cid)
            else:
                raise StageError(
                    "validation", ValueError(f"Unknown request type: {request.get('type')}")
                )

            await self._mark_status(processor_db, request_id, "success", cid)
            await self._publish_update(request_id, "COMPLETED", "DONE", "Processing completed", 1.0)

            logger.info(
                "bg_processing_success",
                extra={
                    "correlation_id": cid,
                    "request_id": request_id,
                    "type": request.get("type"),
                },
            )
        except StageError as exc:
            error_payload = self._build_error_payload(exc.stage, exc.original)
            if request:
                await self._mark_status(
                    processor_db,
                    request_id,
                    "error",
                    correlation_id or request.get("correlation_id"),
                )
            await self._publish_update(
                request_id,
                "FAILED",
                exc.stage.upper(),
                str(exc.original),
                0.0,
                error=str(exc.original),
            )
            logger.error(
                "bg_processing_failed",
                exc_info=True,
                extra={
                    "correlation_id": getattr(request, "correlation_id", correlation_id),
                    "request_id": request_id,
                    **error_payload,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            error_payload = self._build_error_payload("unknown", exc)
            if request:
                await self._mark_status(
                    processor_db,
                    request_id,
                    "error",
                    correlation_id or request.get("correlation_id"),
                )
            await self._publish_update(
                request_id, "FAILED", "UNKNOWN", str(exc), 0.0, error=str(exc)
            )
            logger.error(
                "bg_processing_failed",
                exc_info=True,
                extra={
                    "correlation_id": getattr(request, "correlation_id", correlation_id),
                    "request_id": request_id,
                    **error_payload,
                },
            )
        finally:
            await self._release_lock(lock_handle)

    def _maybe_override_db(
        self, db_path: str | None
    ) -> tuple[DatabaseSessionManager, URLProcessor]:
        if not db_path:
            return self.db, self.url_processor

        override_db = DatabaseSessionManager(
            path=db_path,
            operation_timeout=self.cfg.database.operation_timeout,
            max_retries=self.cfg.database.max_retries,
            json_max_size=self.cfg.database.json_max_size,
            json_max_depth=self.cfg.database.json_max_depth,
            json_max_array_length=self.cfg.database.json_max_array_length,
            json_max_dict_keys=self.cfg.database.json_max_dict_keys,
        )

        override_processor = URLProcessor(
            cfg=self.cfg,
            db=override_db,
            firecrawl=self.url_processor.content_extractor.firecrawl,
            openrouter=self.url_processor.llm_summarizer.openrouter,
            response_formatter=self.url_processor.response_formatter,
            audit_func=self._audit,
            sem=lambda: self._sem,
        )

        return override_db, override_processor

    async def _acquire_lock(self, request_id: int, correlation_id: str | None) -> LockHandle | None:
        if self._lock_enabled and self.redis:
            key = redis_key(self.cfg.redis.prefix, "bg", "req", str(request_id))
            token = f"worker-{time.time_ns()}"
            try:
                acquired = await self.redis.set(key, token, nx=True, px=self._lock_ttl_ms)
            except Exception as exc:
                logger.warning(
                    "bg_lock_redis_error",
                    exc_info=True,
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "error": str(exc),
                    },
                )
                if self._lock_required:
                    raise StageError("lock", exc) from exc
                acquired = False

            if acquired:
                logger.info(
                    "bg_lock_acquired",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                        "ttl_ms": self._lock_ttl_ms,
                    },
                )
                return LockHandle("redis", key, token, None)

            if self._lock_skip_on_held:
                logger.info(
                    "bg_lock_held_skip",
                    extra={
                        "correlation_id": correlation_id,
                        "request_id": request_id,
                        "source": "redis",
                    },
                )
                return None

        lock = self._local_locks.setdefault(request_id, asyncio.Lock())
        if lock.locked() and self._lock_skip_on_held:
            logger.info(
                "bg_lock_held_skip",
                extra={
                    "correlation_id": correlation_id,
                    "request_id": request_id,
                    "source": "local",
                },
            )
            return None

        await lock.acquire()
        logger.info(
            "bg_lock_acquired",
            extra={
                "correlation_id": correlation_id,
                "request_id": request_id,
                "source": "local",
                "ttl_ms": self._lock_ttl_ms,
            },
        )
        return LockHandle("local", str(request_id), None, lock)

    async def _release_lock(self, handle: LockHandle) -> None:
        if not handle:
            return

        if handle.source == "redis" and self.redis:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            try:
                await self.redis.eval(script, 1, handle.key, handle.token)
            except Exception:  # pragma: no cover - best effort
                logger.warning(
                    "bg_lock_release_failed",
                    exc_info=True,
                    extra={"key": handle.key, "source": "redis"},
                )
        elif handle.source == "local" and handle.local_lock and handle.local_lock.locked():
            handle.local_lock.release()

    async def _process_url_type(
        self,
        request_id: int,
        request: dict[str, Any],
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        correlation_id: str,
    ) -> None:
        normalized_url = normalize_url(request.get("input_url") or "")

        await self._publish_update(
            request_id, "PROCESSING", "EXTRACTION", "Extracting content...", 0.2
        )
        content_text, _content_source, _metadata = await self._run_stage(
            "extraction",
            correlation_id,
            lambda: url_processor.content_extractor.extract_content_pure(
                url=normalized_url,
                correlation_id=correlation_id,
            ),
        )

        if not content_text or not content_text.strip():
            raise StageError(
                "extraction", ValueError("Content extraction failed - no content returned")
            )

        detected_lang = request.get("lang_detected") or detect_language(content_text)
        lang = choose_language(self.cfg.runtime.preferred_lang, detected_lang)
        system_prompt = _get_system_prompt(lang)

        await self._publish_update(
            request_id, "PROCESSING", "SUMMARIZATION", "Summarizing content...", 0.5
        )
        summary_json = await self._run_stage(
            "summarization",
            correlation_id,
            lambda: url_processor.llm_summarizer.summarize_content_pure(
                content_text=content_text,
                chosen_lang=lang,
                system_prompt=system_prompt,
                correlation_id=correlation_id,
            ),
        )

        if not summary_json:
            raise StageError(
                "summarization", ValueError("Summary generation failed - no summary returned")
            )

        await self._publish_update(request_id, "PROCESSING", "SAVING", "Saving summary...", 0.9)
        repo = self.summary_repo if db == self.db else SqliteSummaryRepositoryAdapter(db)
        await repo.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=summary_json,
            is_read=False,
        )

    async def _process_forward_type(
        self,
        request_id: int,
        request: dict[str, Any],
        db: DatabaseSessionManager,
        url_processor: URLProcessor,
        correlation_id: str,
    ) -> None:
        lang = request.get("lang_detected") or "auto"
        if lang == "auto":
            content_text = request.get("content_text") or ""
            detected = detect_language(content_text)
            lang = choose_language(self.cfg.runtime.preferred_lang, detected)
        system_prompt = _get_system_prompt(lang)

        await self._publish_update(
            request_id, "PROCESSING", "SUMMARIZATION", "Summarizing content...", 0.5
        )
        summary_json = await self._run_stage(
            "summarization",
            correlation_id,
            lambda: url_processor.llm_summarizer.summarize_content_pure(
                content_text=request.get("content_text") or "",
                chosen_lang=lang,
                system_prompt=system_prompt,
                correlation_id=correlation_id,
            ),
        )

        if not summary_json:
            raise StageError(
                "summarization", ValueError("Summary generation failed - no summary returned")
            )

        await self._publish_update(request_id, "PROCESSING", "SAVING", "Saving summary...", 0.9)
        repo = self.summary_repo if db == self.db else SqliteSummaryRepositoryAdapter(db)
        await repo.async_upsert_summary(
            request_id=request_id,
            lang=lang,
            json_payload=summary_json,
            is_read=False,
        )

    async def _run_stage(
        self,
        stage: str,
        correlation_id: str,
        func: Callable[[], Awaitable[Any]],
    ) -> Any:
        try:
            return await self._run_with_backoff(func, stage, correlation_id)
        except Exception as exc:
            raise StageError(stage, exc) from exc

    async def _run_with_backoff(
        self,
        func: Callable[[], Awaitable[Any]],
        stage: str,
        correlation_id: str,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._retry.attempts + 1):
            try:
                return await func()
            except Exception as exc:
                last_error = exc
                delay_ms = min(
                    self._retry.max_delay_ms,
                    int(self._retry.base_delay_ms * (2 ** (attempt - 1))),
                )
                jitter = int(delay_ms * self._retry.jitter_ratio)
                delay_ms = max(0, delay_ms + random.randint(-jitter, jitter))

                if attempt >= self._retry.attempts:
                    break

                logger.warning(
                    "bg_retry",
                    extra={
                        "correlation_id": correlation_id,
                        "stage": stage,
                        "attempt": attempt,
                        "delay_ms": delay_ms,
                        "error": str(exc),
                    },
                )
                await asyncio.sleep(delay_ms / 1000)

        if last_error:
            raise last_error
        raise RuntimeError("Retry loop exited without result or error")

    async def _has_existing_summary(self, db: DatabaseSessionManager, request_id: int) -> bool:
        repo = self.summary_repo if db == self.db else SqliteSummaryRepositoryAdapter(db)
        try:
            return bool(await repo.async_get_summary_by_request(request_id))
        except Exception:
            return False

    async def _mark_status(
        self, db: DatabaseSessionManager, request_id: int, status: str, correlation_id: str | None
    ) -> None:
        repo = self.request_repo if db == self.db else SqliteRequestRepositoryAdapter(db)
        try:
            await repo.async_update_request_status_with_correlation(
                request_id, status, correlation_id
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "bg_request_status_save_failed",
                exc_info=True,
                extra={"request_id": request_id, "status": status, "error": str(exc)},
            )

    async def _publish_update(
        self,
        request_id: int,
        status: str,
        stage: str,
        message: str,
        progress: float,
        error: str | None = None,
    ) -> None:
        """Publish status update to Redis Pub/Sub."""
        if not self.redis:
            return

        payload = {
            "request_id": request_id,
            "status": status,
            "stage": stage,
            "message": message,
            "progress": progress,
            "error": error,
            "timestamp": time.time(),
        }
        channel = f"processing:request:{request_id}"
        try:
            await self.redis.publish(channel, json.dumps(payload))
        except Exception as exc:
            logger.warning(
                "bg_redis_publish_failed",
                exc_info=True,
                extra={"channel": channel, "error": str(exc)},
            )

    @staticmethod
    def _build_error_payload(stage: str, exc: Exception) -> dict[str, Any]:
        code_map = {
            "extraction": "EXTRACTION_FAILED",
            "summarization": "LLM_FAILED",
            "validation": "VALIDATION_FAILED",
            "lock": "LOCK_FAILED",
        }
        return {
            "error_type": exc.__class__.__name__,
            "error_code": code_map.get(stage, "UNKNOWN_ERROR"),
            "error_message": str(exc),
            "error_stage": stage,
        }


_default_processor: BackgroundProcessor | None = None
_default_lock = asyncio.Lock()


async def _get_default_processor() -> BackgroundProcessor:
    global _default_processor
    if _default_processor:
        return _default_processor

    async with _default_lock:
        if _default_processor:
            return _default_processor

        cfg = load_config()
        redis_client = await get_redis(cfg)
        from app.di.background import build_background_processor

        _default_processor = await build_background_processor(cfg, redis_client=redis_client)
        return _default_processor


async def process_url_request(
    request_id: int, db_path: str | None = None, correlation_id: str | None = None
) -> None:
    processor = await _get_default_processor()
    task = asyncio.create_task(
        processor.process(request_id, correlation_id=correlation_id, db_path=db_path)
    )
    # Background processing tasks - store reference if needed or use fire-and-forget safely
    if not hasattr(processor, "_processing_tasks"):
        processor._processing_tasks = set()  # type: ignore[attr-defined]
    tasks = processor._processing_tasks  # type: ignore[attr-defined]
    tasks.add(task)
    task.add_done_callback(tasks.discard)
