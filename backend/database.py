from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    return create_async_engine(
        settings.database_url,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def reinit_engine() -> None:
    """Recreate the engine and session factory bound to the current event loop.

    Must be called in worker subprocesses (LiveKit agent workers) before any
    DB access, because the module-level engine is created in the parent process's
    event loop and asyncpg connections are loop-bound.
    """
    global engine, AsyncSessionLocal
    engine = _make_engine()
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
