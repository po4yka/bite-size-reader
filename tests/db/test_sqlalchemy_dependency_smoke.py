from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def test_sqlalchemy_async_dependency_imports() -> None:
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost:5432/db")
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    assert select(1) is not None
    assert session_factory.class_ is AsyncSession
