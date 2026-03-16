import asyncio
import logging

from app.config import load_config
from app.core.logging_utils import get_logger
from app.di.database import build_runtime_database
from app.grpc.server_app import ProcessingGrpcServer

logger = get_logger(__name__)


async def serve() -> None:
    cfg = load_config()

    db = build_runtime_database(cfg, connect=True)
    server = ProcessingGrpcServer(cfg=cfg, db=db)
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
