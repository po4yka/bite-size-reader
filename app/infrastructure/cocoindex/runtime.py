"""CocoIndex runtime lifecycle manager.

Owns the CocoIndex process-level init, flow setup, and FlowLiveUpdater
lifecycle. Designed to be instantiated inside the FastAPI lifespan context
manager; a startup failure must not prevent the API from serving requests.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.config.integrations import CocoIndexConfig

logger = get_logger(__name__)


class CocoIndexRuntime:
    """Manages CocoIndex init, flow setup, and live updater lifecycle."""

    def __init__(
        self,
        *,
        cfg: Any,  # AppConfig -- avoid circular import with TYPE_CHECKING
        collection_name: str,
    ) -> None:
        self._cfg = cfg
        self._collection_name = collection_name
        self._updater: Any | None = None
        self._flow: Any | None = None

    async def start(self) -> None:
        """Initialise CocoIndex and start the FlowLiveUpdater."""
        import cocoindex  # noqa: PLC0415

        coco_cfg: CocoIndexConfig = self._cfg.cocoindex
        db_cfg = self._cfg.database

        # Build psycopg3 DSN -- strip asyncpg driver prefix if present
        dsn = coco_cfg.dsn_override or db_cfg.dsn
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

        cocoindex.init(
            cocoindex.Settings(
                database_url=dsn,
                target_schema="cocoindex",
            )
        )

        qdrant_cfg = self._cfg.vector_store

        from app.infrastructure.cocoindex.flow import build_summaries_flow

        self._flow = build_summaries_flow(
            collection_name=self._collection_name,
            qdrant_url=qdrant_cfg.url,
            qdrant_api_key=qdrant_cfg.api_key,
            user_scope=qdrant_cfg.user_scope,
            environment=qdrant_cfg.environment,
            listen_channel=coco_cfg.listen_notify_channel,
        )

        # setup() is idempotent -- creates CocoIndex metadata tables on first run
        await asyncio.to_thread(self._flow.setup)
        logger.info("cocoindex_flow_ready", extra={"collection": self._collection_name})

        # Start live updater in background
        live_updater_cls = cocoindex.FlowLiveUpdater
        self._updater = live_updater_cls(
            self._flow,
            cocoindex.FlowLiveUpdaterOptions(live_mode=True),
        )
        await asyncio.to_thread(self._updater.__enter__)
        logger.info("cocoindex_live_updater_started")

    async def stop(self, timeout: float = 10.0) -> None:
        """Stop the live updater with a bounded timeout."""
        if self._updater is None:
            return
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._updater.__exit__, None, None, None),
                timeout=timeout,
            )
            logger.info("cocoindex_live_updater_stopped")
        except TimeoutError:
            logger.warning(
                "cocoindex_live_updater_stop_timeout",
                extra={"timeout_sec": timeout},
            )
        except Exception:
            logger.exception("cocoindex_live_updater_stop_error")
        finally:
            self._updater = None

    async def run_one_shot(self) -> None:
        """Run a single full-scan update (for CLI backfill delegation)."""
        if self._flow is None:
            raise RuntimeError("CocoIndexRuntime.start() must be called before run_one_shot()")
        await asyncio.to_thread(self._flow.update)
        logger.info("cocoindex_one_shot_complete", extra={"collection": self._collection_name})
