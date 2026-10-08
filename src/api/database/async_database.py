from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, DisconnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

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

logger.info(
    "Async database configuration initialized",
    extra={"database_url": ASYNC_DATABASE_URL.split("@")[-1] if ASYNC_DATABASE_URL else None},
)

# ---------------------------------------------------------------------------
# Pool settings from env (via Settings) — no more hardcoded values
# ---------------------------------------------------------------------------
_pool_size = settings.POSTGRES_POOL_SIZE  # default 10
_max_overflow = settings.POSTGRES_MAX_OVERFLOW  # default 15
_pool_timeout = settings.POSTGRES_POOL_TIMEOUT  # default 30
_pool_recycle = settings.POSTGRES_POOL_RECYCLE  # default 1800

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
    pool_pre_ping=False,  # Must be False — see above
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


async def _close_session(session: AsyncSession) -> None:
    """Close a session whose connection the server may already have dropped.

    Closing rolls back the open transaction; on a connection the database
    closed (idle timeout, compute suspend, network) that rollback raises, and
    the request whose work is already done failed with a 500. The connection
    is invalidated instead, so the pool discards it rather than handing it on.
    """
    try:
        await session.close()
    except DBAPIError as exc:
        logger.warning("Discarding a database connection closed by the server: %s", exc)
        try:
            await session.invalidate()
        except Exception:  # noqa: BLE001 - already unusable; nothing left to release
            pass


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
        await _close_session(session)


import asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from sqlalchemy import event  # noqa: E402


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
        await _close_session(session)


# ============================================================================
# POOLED ASYNC DATABASE (for LangGraph nodes, dispatched onto the main loop)
# ============================================================================

_LANGGRAPH_DB_CONNECT_ATTEMPTS = 3


@asynccontextmanager
async def get_pooled_langgraph_db_context():
    """
    Async context manager for LangGraph nodes, backed by the same bounded,
    reused connection pool as get_async_db_context() (async_engine) instead
    of the unbounded per-call NullPool below.

    Must be entered on the main event loop — from a worker loop, wrap the
    call in src.utils.loop_bridge.run_on_main_loop(). The pool's connections
    are not safe to check out from a different loop than the one that
    created them.

    Retries only the initial connection handshake on a transient SASL
    protocol violation — that step is idempotent (nothing has executed yet),
    so retrying it never risks a duplicate write. The caller's body is never
    retried.
    """
    session = None
    for attempt in range(1, _LANGGRAPH_DB_CONNECT_ATTEMPTS + 1):
        session = AsyncSessionLocal()
        try:
            await session.connection()
            break
        except Exception as exc:
            await session.close()
            if not _is_sasl_protocol_error(exc) or attempt == _LANGGRAPH_DB_CONNECT_ATTEMPTS:
                raise
            logger.warning(
                "DIAGNOSTIC: SASL Protocol Violation on connect, retrying",
                extra={"error_detail": str(exc), "attempt": attempt},
            )

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
                "DIAGNOSTIC: SASL Protocol Violation caught in get_pooled_langgraph_db_context",
                extra={"error_detail": str(exc), "loop_id": loop_id},
                exc_info=True,
            )
        raise
    finally:
        await session.close()


# ============================================================================
# ASYNC DATABASE (for LangGraph nodes running in different event loops)
# ============================================================================
#
# NOTE: kept in place, unused by call sites (migrated to
# get_pooled_langgraph_db_context above), as a fallback primitive. Safe
# on its own — NullPool never crosses loops mid-connection — just exposed
# to a fresh SCRAM handshake on every call, which is what made a transient
# auth blip fatal instead of absorbed by a reused connection.

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
# No request on a connection that is still inside a transaction
# ---------------------------------------------------------------------------
#
# A pooled connection must be idle between requests. If one goes back to the pool inside a
# transaction the engine knows nothing of, the driver turns every later request's BEGIN into
# a SAVEPOINT and its COMMIT into a RELEASE: the request is answered as done, its rows are
# visible on that one connection only, and they are gone when the process ends
# (revnix/rext-control#858: sign-ins answered 200 whose session no other request could find,
# a workspace created with a 201 that never became a row). SQLAlchemy's own return-to-pool
# rollback does not cover it, because it only ends transactions it began itself.
#
# So the pool is checked at both doors. A connection returned inside a transaction is
# dropped there, with the stack of whoever returned it in the log; and one found so when it
# is asked for is dropped and another is handed out.


def _inside_a_transaction(dbapi_connection) -> bool:
    """Whether the driver's connection is inside a transaction: by the server's last word,
    or by the driver's own record of one it began."""
    driver = getattr(dbapi_connection, "driver_connection", None)
    if driver is None:
        return False
    try:
        return bool(driver.is_in_transaction()) or getattr(driver, "_top_xact", None) is not None
    except Exception:  # noqa: BLE001 - a closed or foreign connection is not this guard's
        return False


def guard_pool_against_open_transactions(engine) -> None:
    """Keep `engine`'s pool from handing a request a connection that is inside a transaction."""

    @event.listens_for(engine.sync_engine, "checkin")
    def _drop_a_connection_returned_inside_a_transaction(dbapi_connection, connection_record):
        if dbapi_connection is not None and _inside_a_transaction(dbapi_connection):
            logger.error(
                "DB_GUARD: a connection went back to the pool inside a transaction; it is dropped",
                stack_info=True,
            )
            connection_record.invalidate()

    @event.listens_for(engine.sync_engine, "checkout")
    def _never_hand_out_a_connection_inside_a_transaction(
        dbapi_connection, connection_record, connection_proxy
    ):
        if _inside_a_transaction(dbapi_connection):
            logger.error(
                "DB_GUARD: a pooled connection was inside a transaction when asked for; "
                "it is dropped and another is used"
            )
            raise DisconnectionError("a pooled connection was still inside a transaction")


guard_pool_against_open_transactions(async_engine)


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
    logger.debug(
        "DB_DIAG: langgraph_async_engine opened new raw connection", extra={"loop_id": loop_id}
    )


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
