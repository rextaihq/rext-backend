"""Base utilities for seed scripts."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.api.config import get_settings


@asynccontextmanager
async def get_seed_session():
    """Create an async database session for seeding."""
    settings = get_settings()
    db_url = settings.POSTGRES_URI_CUSTOM
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url, echo=False)
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
