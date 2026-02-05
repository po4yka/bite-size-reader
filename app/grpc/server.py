import asyncio
import logging

from app.config import load_config
from app.core.logging_utils import get_logger
from app.grpc.bootstrap import create_database
from app.grpc.server_app import ProcessingGrpcServer

logger = get_logger(__name__)


async def serve() -> None:
    cfg = load_config()

    db = create_database(cfg)
    server = ProcessingGrpcServer(cfg=cfg, db=db)
    await server.start()
    await server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
