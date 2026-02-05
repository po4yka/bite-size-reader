"""gRPC server application wrapper (lifecycle + wiring)."""

from __future__ import annotations

import asyncio
from concurrent import futures
from typing import TYPE_CHECKING

import grpc

from app.api.dependencies import search_resources
from app.core.logging_utils import get_logger
from app.grpc.service import ProcessingService
from app.grpc.shutdown import ShutdownCoordinator, install_signal_handlers
from app.infrastructure.redis import close_redis
from app.protos import processing_pb2_grpc

if TYPE_CHECKING:
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = get_logger(__name__)

DEFAULT_LISTEN_ADDR = "[::]:50051"
DEFAULT_MAX_WORKERS = 10
DEFAULT_SHUTDOWN_GRACE_SECONDS = 5


class ProcessingGrpcServer:
    """Lifecycle wrapper for the Processing gRPC server."""

    def __init__(
        self,
        *,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        listen_addr: str = DEFAULT_LISTEN_ADDR,
        max_workers: int = DEFAULT_MAX_WORKERS,
        shutdown_grace_seconds: int = DEFAULT_SHUTDOWN_GRACE_SECONDS,
    ) -> None:
        self._cfg = cfg
        self._db = db
        self._listen_addr = listen_addr
        self._shutdown_grace_seconds = shutdown_grace_seconds

        self._server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=max_workers))
        self._shutdown = ShutdownCoordinator(self.stop)
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        service = ProcessingService(self._cfg, self._db)
        processing_pb2_grpc.add_ProcessingServiceServicer_to_server(service, self._server)

        self._server.add_insecure_port(self._listen_addr)
        logger.info("grpc_server_starting", extra={"listen_addr": self._listen_addr})

        await self._server.start()

        loop = asyncio.get_running_loop()
        install_signal_handlers(loop, self._shutdown)

    async def wait_for_termination(self) -> None:
        await self._server.wait_for_termination()

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True

        logger.info("grpc_server_stopping", extra={"grace_seconds": self._shutdown_grace_seconds})
        await self._server.stop(self._shutdown_grace_seconds)

        await search_resources.shutdown_chroma_search_resources()
        await close_redis()
        self._db.database.close()

        logger.info("grpc_server_stopped")
