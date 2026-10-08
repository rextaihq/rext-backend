"""No request runs on a pooled connection that is still inside a transaction (rext-control#858).

Seen on staging on 8 October 2026: sign-ins answered 200 whose session no other request could
find, and a workspace created with a 201 that never became a row. A pooled connection left
inside a transaction the engine doesn't know of does exactly that: the driver turns the next
request's BEGIN into a SAVEPOINT and its COMMIT into a RELEASE, so the request is answered as
done, its rows are visible on that one connection only, and they are gone when the process ends.

On the test PostgreSQL, with a pool of one so the next request gets the same connection.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, Table, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import (
    _inside_a_transaction,
    guard_pool_against_open_transactions,
)
from tests.conftest import TEST_DATABASE_URL

ACTIVITY = text(
    "select state from pg_stat_activity "
    "where datname = current_database() and pid <> pg_backend_pid() and application_name = :name"
)


@pytest_asyncio.fixture
async def scratch():
    """A scratch table, an onlooker's connection, and a name to find this test's connections by."""
    tag = uuid.uuid4().hex[:10]
    table = Table(f"zz_pool_guard_{tag}", MetaData(), Column("note", Text))
    # Each of the onlooker's statements stands alone, so it always reads what is committed now.
    looking = create_async_engine(
        TEST_DATABASE_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with looking.connect() as onlooker:
            await onlooker.run_sync(table.create)
            try:
                yield onlooker, table, f"pool-guard-{tag}"
            finally:
                await onlooker.run_sync(table.drop, checkfirst=True)
    finally:
        await looking.dispose()


async def _states(onlooker, name: str) -> list[str]:
    """The states of this test's connections, as the server sees them."""
    return list((await onlooker.execute(ACTIVITY, {"name": name})).scalars())


async def _rows(onlooker, table: Table) -> int:
    """The rows another connection can see."""
    return (await onlooker.execute(select(func.count()).select_from(table))).scalar_one()


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


async def _a_request_that_commits(engine, table: Table, note: str) -> None:
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessions() as session:
        await session.execute(table.insert().values(note=note))
        await session.commit()


@pytest.mark.asyncio
async def test_without_the_guard_a_commit_on_such_a_connection_saves_nothing(scratch):
    """The fault itself, so the guard's test below is known to test something."""
    onlooker, table, name = scratch
    engine = _engine(name)
    try:
        await _leave_the_pooled_connection_inside_a_transaction(engine)
        assert await _states(onlooker, name) == ["idle in transaction"]

        await _a_request_that_commits(engine, table, "answered as done")

        assert await _rows(onlooker, table) == 0
    finally:
        await engine.dispose()
    assert await _rows(onlooker, table) == 0  # and gone for good


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
        assert "idle in transaction" not in await _states(onlooker, name)

        await _a_request_that_commits(engine, table, "saved")

        assert await _rows(onlooker, table) == 1
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
        assert await _rows(onlooker, table) == 1
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
        assert await _rows(onlooker, table) == 3
        # One connection served all three: nothing was dropped.
        assert len(await _states(onlooker, name)) == 1
    finally:
        await engine.dispose()


def test_a_connection_with_no_driver_is_not_this_guards():
    assert _inside_a_transaction(object()) is False
    assert _inside_a_transaction(None) is False
