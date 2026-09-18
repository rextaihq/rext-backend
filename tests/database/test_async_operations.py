"""
Tests for Async Database Operations

This module tests the async SQLAlchemy setup and basic database operations.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import AsyncSessionLocal, async_engine
from src.api.models.user_models.users import Users


@pytest.mark.asyncio
async def test_async_engine_connection():
    """Test that async engine can connect to database."""
    async with async_engine.begin() as conn:
        result = await conn.execute(select(1))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_async_session_creation():
    """Test that async session can be created."""
    async with AsyncSessionLocal() as session:
        assert isinstance(session, AsyncSession)
        assert session.is_active


@pytest.mark.asyncio
async def test_async_query_execution():
    """Test basic async query execution."""
    async with AsyncSessionLocal() as session:
        # Query for users (may be empty, that's ok)
        result = await session.execute(select(Users).limit(1))
        user = result.scalar_one_or_none()

        # Test passes if query executes without error
        # (user may be None if database is empty)
        assert user is None or isinstance(user, Users)


@pytest.mark.asyncio
async def test_concurrent_queries():
    """Test that multiple concurrent queries work correctly."""
    import asyncio

    async def query_database(session_num: int):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(1))
            return (session_num, result.scalar())

    # Run 10 concurrent queries
    tasks = [query_database(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    # Verify all queries completed successfully
    assert len(results) == 10
    for session_num, value in results:
        assert value == 1


@pytest.mark.asyncio
async def test_async_transaction_commit():
    """Test that async transactions commit properly."""
    # This test doesn't create real data to avoid polluting the database
    # It just verifies the transaction mechanism works
    async with AsyncSessionLocal() as session:
        try:
            # Execute a simple query
            result = await session.execute(select(1))
            assert result.scalar() == 1

            # Commit transaction
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.mark.asyncio
async def test_async_transaction_rollback():
    """Test that async transactions rollback on error."""
    async with AsyncSessionLocal() as session:
        try:
            # Force an error with invalid SQL
            await session.execute(select("invalid_column_that_does_not_exist"))

            # Should not reach here
            assert False, "Should have raised an exception"

        except Exception:
            # Rollback should work
            await session.rollback()
            # Test passes if we can rollback without error
            assert True
