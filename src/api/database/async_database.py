from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
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

# ---------------------------------------------------------------------------
# Pool settings from env (via Settings) — no more hardcoded values
# ---------------------------------------------------------------------------
_pool_size = settings.POSTGRES_POOL_SIZE          # default 10
_max_overflow = settings.POSTGRES_MAX_OVERFLOW    # default 15
_pool_timeout = settings.POSTGRES_POOL_TIMEOUT    # default 30
_pool_recycle = settings.POSTGRES_POOL_RECYCLE    # default 1800

logger.info(
    "DB pool config",
    extra={
        "pool_size": _pool_size,
        "max_overflow": _max_overflow,
        "pool_timeout": _pool_timeout,
        "pool_recycle": _pool_recycle,
    },
)

# Create async engine
# IMPORTANT: pool_pre_ping=False — enabling it causes asyncpg to run async I/O
# from thread-pool threads (when LangGraph dispatches sync nodes), which raises:
# RuntimeError: Task got Future attached to a different loop.
async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    isolation_level="READ COMMITTED",
    pool_pre_ping=False,   # Must be False — see above
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_recycle=_pool_recycle,
    pool_timeout=_pool_timeout,
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
import asyncio
from sqlalchemy import event

def _is_sasl_protocol_error(exc: Exception) -> bool:
    err_str = str(exc).lower()
    return "sasl authentication failed" in err_str or "protocolviolationerror" in err_str

# Context manager for background tasks
@asynccontextmanager
async def get_async_db_context():
    """
    Async context manager for background tasks and standalone operations.

    Returns an async context manager that provides a database session with
    automatic transaction handling (commit on success, rollback on error).
    Includes automatic single-retry for transient SASL protocol violations.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if _is_sasl_protocol_error(exc):
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                loop_id = "no_loop"
            logger.error(
                "DIAGNOSTIC: SASL Protocol Violation caught in get_async_db_context",
                extra={"error_detail": str(exc), "loop_id": loop_id},
                exc_info=True,
            )
        raise
    finally:
        await session.close()


# ============================================================================
# ASYNC DATABASE (for LangGraph nodes running in different event loops)
# ============================================================================

# Use NullPool for LangGraph tasks since they run in background thread loops
# which causes `RuntimeError: Task got Future attached to a different loop`
# when reusing connections from the main global QueuePool.
langgraph_async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    isolation_level="READ COMMITTED",
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
)

LanggraphAsyncSessionLocal = async_sessionmaker(
    langgraph_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Diagnostic event listeners for connection telemetry
# ---------------------------------------------------------------------------
@event.listens_for(async_engine.sync_engine, "connect")
def _log_async_engine_connect(dbapi_connection, connection_record):
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = "no_loop"
    logger.debug("DB_DIAG: async_engine opened new raw connection", extra={"loop_id": loop_id})

@event.listens_for(langgraph_async_engine.sync_engine, "connect")
def _log_langgraph_engine_connect(dbapi_connection, connection_record):
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = "no_loop"
    logger.debug("DB_DIAG: langgraph_async_engine opened new raw connection", extra={"loop_id": loop_id})


@asynccontextmanager
async def get_langgraph_async_db_context():
    """
    Async context manager for LangGraph nodes running in different event loops.
    Uses NullPool to prevent Future attached to different loop errors.
    Logs structured telemetry on SASL protocol errors.
    """
    session = LanggraphAsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if _is_sasl_protocol_error(exc):
            try:
                loop_id = id(asyncio.get_running_loop())
            except RuntimeError:
                loop_id = "no_loop"
            logger.error(
                "DIAGNOSTIC: SASL Protocol Violation caught in get_langgraph_async_db_context",
                extra={"error_detail": str(exc), "loop_id": loop_id},
                exc_info=True,
            )
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
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_recycle=_pool_recycle,
    pool_timeout=_pool_timeout,
    connect_args={"prepare_threshold": 10},  # Required for PgBouncer transaction mode
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

