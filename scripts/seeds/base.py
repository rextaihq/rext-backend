"""Base utilities for seed scripts."""

from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.config import get_settings

# The connection every seed writes on while seeding_on() is open (the server's start).
_seeding_connection: ContextVar[Optional[AsyncConnection]] = ContextVar(
    "seeding_connection", default=None
)


@asynccontextmanager
async def seeding_on(connection: AsyncConnection):
    """Every seed in this block writes in the connection's transaction: the caller
    commits them all, or none of them is kept."""
    token = _seeding_connection.set(connection)
    try:
        yield
    finally:
        _seeding_connection.reset(token)


@asynccontextmanager
async def get_seed_session():
    """Create an async database session for seeding."""
    connection = _seeding_connection.get()
    if connection is not None:
        # A savepoint in the caller's transaction: its commit keeps the seed, not this one.
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return

    settings = get_settings()
    db_url = settings.POSTGRES_URI_CUSTOM
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    # The address may go through PgBouncer in transaction mode, as the app's engine does.
    engine = create_async_engine(db_url, echo=False, connect_args={"statement_cache_size": 0})
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


def utc_now() -> datetime:
    """Return current UTC datetime (naive UTC for DB compatibility)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
