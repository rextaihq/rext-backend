"""
Cached LangGraph Workflow Singleton

Provides a cached, compiled LangGraph workflow with AsyncPostgresSaver
checkpointer for state persistence across workflow runs.

Lifecycle:
    1. Call `await initialize_workflow(conn_string)` during app startup
    2. Call `create_workflow()` to get the cached compiled workflow
    3. Call `await shutdown_workflow()` during app shutdown
"""

import asyncio
import logging

from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

_compiled_workflow = None
_checkpointer = None
_pool = None


async def initialize_workflow(conn_string: str) -> None:
    """Initialize the checkpointer and compile the workflow.

    Creates an AsyncConnectionPool, sets up checkpoint tables in PostgreSQL,
    and compiles the LangGraph workflow once for reuse across all requests.

    Args:
        conn_string: PostgreSQL connection URI (e.g. postgresql://user:pass@host/db)
    """
    global _compiled_workflow, _checkpointer, _pool

    try:
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from src.flow.engines.rext import create_rext_engine

        _pool = AsyncConnectionPool(conninfo=conn_string, open=False)
        await _pool.open()

        _checkpointer = AsyncPostgresSaver(conn=_pool)
        await _checkpointer.setup()

        _compiled_workflow = create_rext_engine(checkpointer=_checkpointer)
        logger.info("LangGraph workflow initialized with AsyncPostgresSaver")

    except Exception as e:
        logger.warning(f"Failed to initialize AsyncPostgresSaver, falling back to MemorySaver: {e}")
        from src.flow.engines.rext import create_rext_engine
        _checkpointer = MemorySaver()
        _compiled_workflow = create_rext_engine(checkpointer=_checkpointer)


async def shutdown_workflow() -> None:
    """Close the connection pool during app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("LangGraph workflow connection pool closed")


def create_workflow():
    """Return the cached compiled workflow.

    If initialize_workflow() was not called (e.g. in development or tests),
    falls back to compiling with MemorySaver.
    """
    global _compiled_workflow
    if _compiled_workflow is None:
        logger.warning("Workflow not initialized via startup; compiling with MemorySaver fallback")
        from src.flow.engines.rext import create_rext_engine
        _compiled_workflow = create_rext_engine(checkpointer=MemorySaver())
    return _compiled_workflow
