from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from src.api.config import get_settings
from src.utils.logger import logger

# Get settings instance
settings = get_settings()

# Get database URL and convert to async URL
SQLALCHEMY_DATABASE_URL = settings.POSTGRES_URI_CUSTOM

# Convert postgresql:// to postgresql+asyncpg://
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    ASYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL

logger.info("Async database configuration initialized", extra={"database_url": ASYNC_DATABASE_URL.split("@")[-1] if ASYNC_DATABASE_URL else None})

# Create async engine
# IMPORTANT: pool_pre_ping=False — enabling it causes asyncpg to run async I/O
# from thread-pool threads (when LangGraph dispatches sync nodes), which raises:
# RuntimeError: Task got Future attached to a different loop.
# pool_size reduced to prevent "too many clients" on the server's shared Postgres.
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=False,   # Must be False — see above
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    pool_timeout=30,
    connect_args={"statement_cache_size": 0},  # Required for PgBouncer transaction mode
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    # autoflush defaults to True - let SQLAlchemy handle flushing
    # autocommit defaults to False - we manage transactions explicitly
)

# Async dependency for FastAPI
async def get_async_db():
    """
    Async database session dependency for FastAPI routes.

    Yields a database session and ensures proper cleanup.
    The decorator handles commit/rollback.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()


from contextlib import asynccontextmanager

# Context manager for background tasks
@asynccontextmanager
async def get_async_db_context():
    """
    Async context manager for background tasks and standalone operations.

    Returns an async context manager that provides a database session with
    automatic transaction handling (commit on success, rollback on error).

    Usage:
        async with get_async_db_context() as db:
            # Use db session
            await db.execute(...)
            # Automatically commits on exit if no exception

    This is specifically designed for FastAPI background tasks which need
    their own database session independent of the request lifecycle.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ============================================================================
# SYNC DATABASE (for LangGraph nodes running in thread pool)
# ============================================================================

# Convert postgresql:// to postgresql+psycopg:// for sync engine (using psycopg3)
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    SYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
else:
    SYNC_DATABASE_URL = SQLALCHEMY_DATABASE_URL

# Create sync engine for LangGraph nodes
sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    pool_timeout=30,
    connect_args={"prepare_threshold": None},  # Required for PgBouncer transaction mode
)

# Create sync session factory
SyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
)


def get_sync_db():
    """
    Synchronous database session generator for LangGraph nodes.

    LangGraph nodes run in a thread pool executor (synchronous context),
    so they need synchronous database sessions.

    Usage:
        db = next(get_sync_db())
        try:
            # Use db session
            db.query(...)
        finally:
            db.close()
    """
    db = SyncSessionLocal()
    try:
        yield db
    finally:
        db.close()
