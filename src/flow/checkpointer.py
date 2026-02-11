"""Checkpointer factory for LangGraph workflow persistence.

Provides a PostgreSQL-backed checkpointer for persisting workflow state
when invoking the REXT graph directly (outside the LangGraph Platform).
The LangGraph Platform uses its own checkpointer configured via langgraph.json.
"""

import logging
import os

logger = logging.getLogger(__name__)

_checkpointer = None


async def get_checkpointer():
    """Get or create the PostgreSQL checkpointer singleton.

    Uses POSTGRES_URI_CUSTOM or DATABASE_URL for the connection string.
    Falls back to MemorySaver if no database URL is available.
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    db_url = os.environ.get("POSTGRES_URI_CUSTOM") or os.environ.get("DATABASE_URL")

    if not db_url:
        logger.warning("No database URL found, using MemorySaver as fallback")
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        return _checkpointer

    # Convert postgresql:// to postgresql+psycopg:// for async support if needed
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    _checkpointer = AsyncPostgresSaver.from_conn_string(db_url)
    await _checkpointer.setup()
    logger.info("PostgreSQL checkpointer initialized")
    return _checkpointer
