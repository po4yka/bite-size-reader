import asyncio
import logging
import signal
from concurrent import futures

import grpc

from app.api.dependencies import search_resources
from app.config import load_config
from app.core.logging_utils import get_logger
from app.db.database import Database
from app.grpc.service import ProcessingService
from app.infrastructure.redis import close_redis
from app.protos import processing_pb2_grpc

logger = get_logger(__name__)


async def serve():
    cfg = load_config()

    # Initialize DB
    db = Database(
        path=cfg.database.path,
        operation_timeout=cfg.database.operation_timeout,
        max_retries=cfg.database.max_retries,
        json_max_size=cfg.database.json_max_size,
        json_max_depth=cfg.database.json_max_depth,
        json_max_array_length=cfg.database.json_max_array_length,
        json_max_dict_keys=cfg.database.json_max_dict_keys,
    )
    # The Database class handles connection on init via proxy or lazily?
    # app/api/main.py does explicit connect: _db._database.connect(reuse_if_open=True)
    # Let's do the same to be safe, though Peewee usually auto-connects.
    db._database.connect(reuse_if_open=True)
    logger.info("database_initialized", extra={"db_path": cfg.database.path})

    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))

    service = ProcessingService(cfg, db)
    processing_pb2_grpc.add_ProcessingServiceServicer_to_server(service, server)

    listen_addr = "[::]:50051"
    # Could make port configurable via env vars if needed

    server.add_insecure_port(listen_addr)
    logger.info(f"Starting gRPC server on {listen_addr}")

    await server.start()

    # Graceful shutdown handler
    async def shutdown():
        logger.info("Shutting down gRPC server...")
        await server.stop(5)
        await search_resources.shutdown_chroma_search_resources()
        await close_redis()
        db._database.close()
        logger.info("Shutdown complete")

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
