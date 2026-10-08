"""No request runs on a pooled connection that is still inside a transaction (rext-control#858).

Seen on staging on 8 October 2026: sign-ins answered 200 whose session no other request could
find, and a workspace created with a 201 that never became a row. A pooled connection left
inside a transaction the engine doesn't know of does exactly that: the driver turns the next
request's BEGIN into a SAVEPOINT and its COMMIT into a RELEASE, so the request is answered as
done, its rows are visible on that one connection only, and they are gone when the process ends.

On the test PostgreSQL, with a pool of one so the next request gets the same connection.
"""

import uuid

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.database.async_database import (
    _inside_a_transaction,
    guard_pool_against_open_transactions,
)
from tests.conftest import TEST_DATABASE_URL

ACTIVITY = (
    "select state from pg_stat_activity "
    "where datname = current_database() and pid <> pg_backend_pid() and application_name = $1"
)


@pytest_asyncio.fixture
async def scratch():
    """A scratch table, an onlooker's connection, and a name to find this test's connections by."""
    onlooker = await asyncpg.connect(
        TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    )
    table = f"zz_pool_guard_{uuid.uuid4().hex[:10]}"
    await onlooker.execute(f"create table {table} (note text)")
    try:
        yield onlooker, table, f"pool-guard-{table[-10:]}"
    finally:
        await onlooker.execute(f"drop table if exists {table}")
        await onlooker.close()


def _engine(name: str):
    return create_async_engine(
        TEST_DATABASE_URL,
        isolation_level="READ COMMITTED",
        pool_pre_ping=False,
        pool_size=1,
        max_overflow=0,
        connect_args={"statement_cache_size": 0, "server_settings": {"application_name": name}},
    )


async def _leave_the_pooled_connection_inside_a_transaction(engine) -> None:
    """A transaction begun on the driver's own connection and never ended, as a failed begin leaves it."""
    async with engine.connect() as connection:
        driver = (await connection.get_raw_connection()).driver_connection
        await driver.transaction().start()


async def _a_request_that_commits(engine, table: str, note: str) -> None:
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(text(f"insert into {table} values (:note)"), {"note": note})
        await session.commit()


@pytest.mark.asyncio
async def test_without_the_guard_a_commit_on_such_a_connection_saves_nothing(scratch):
    """The fault itself, so the guard's test below is known to test something."""
    onlooker, table, name = scratch
    engine = _engine(name)
    try:
        await _leave_the_pooled_connection_inside_a_transaction(engine)
        assert [r["state"] for r in await onlooker.fetch(ACTIVITY, name)] == ["idle in transaction"]

        await _a_request_that_commits(engine, table, "answered as done")

        assert await onlooker.fetchval(f"select count(*) from {table}") == 0
    finally:
        await engine.dispose()
    assert await onlooker.fetchval(f"select count(*) from {table}") == 0  # and gone for good


@pytest.mark.asyncio
async def test_a_connection_returned_inside_a_transaction_is_dropped(scratch, caplog):
    onlooker, table, name = scratch
    engine = _engine(name)
    guard_pool_against_open_transactions(engine)
    try:
        with caplog.at_level("ERROR"):
            await _leave_the_pooled_connection_inside_a_transaction(engine)

        assert any(
            "went back to the pool inside a transaction" in r.getMessage() for r in caplog.records
        )
        assert "idle in transaction" not in [
            r["state"] for r in await onlooker.fetch(ACTIVITY, name)
        ]

        await _a_request_that_commits(engine, table, "saved")

        assert await onlooker.fetchval(f"select count(*) from {table}") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_connection_found_inside_a_transaction_is_not_handed_out(scratch, caplog):
    """One that got into that state while it sat in the pool: caught when it is asked for."""
    onlooker, table, name = scratch
    engine = _engine(name)
    try:
        await _leave_the_pooled_connection_inside_a_transaction(engine)  # no guard yet: it stays
        guard_pool_against_open_transactions(engine)

        with caplog.at_level("ERROR"):
            await _a_request_that_commits(engine, table, "saved")

        assert any("inside a transaction when asked for" in r.getMessage() for r in caplog.records)
        assert await onlooker.fetchval(f"select count(*) from {table}") == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_idle_connection_is_left_alone(scratch, caplog):
    onlooker, table, name = scratch
    engine = _engine(name)
    guard_pool_against_open_transactions(engine)
    try:
        with caplog.at_level("ERROR"):
            for n in range(3):
                await _a_request_that_commits(engine, table, f"request {n}")
        assert not [r for r in caplog.records if "DB_GUARD" in r.getMessage()]
        assert await onlooker.fetchval(f"select count(*) from {table}") == 3
        # One connection served all three: nothing was dropped.
        assert len(await onlooker.fetch(ACTIVITY, name)) == 1
    finally:
        await engine.dispose()


def test_a_connection_with_no_driver_is_not_this_guards():
    assert _inside_a_transaction(object()) is False
    assert _inside_a_transaction(None) is False
