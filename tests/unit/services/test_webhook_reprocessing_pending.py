"""The reprocessing job also recovers an event stored but never processed (F11, #336).

The route stores each Lemon Squeezy event before acknowledging it, so a process
that stopped after the 200 leaves the row unprocessed with no error, and Lemon
Squeezy won't send it again. Checked on the test PostgreSQL inside a rolled-back
transaction.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.tasks import webhook_reprocessing_task as task
from tests.conftest import TEST_DATABASE_URL


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[WebhookEvent.__table__], checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


def _event(db, *, minutes_ago, processed=False, error=None, retries=0):
    # From the clock when the event is made, not a time fixed at import: in a long run, a
    # "one minute ago" event timed at import was already past the wait (G44.17,
    # revnix/rext-control#638).
    at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    row = WebhookEvent(
        event_id=f"wh-{uuid4().hex[:8]}",
        event_name="subscription_updated",
        payload={},
        processed=processed,
        error_message=error,
        retry_count=retries,
        created_at=at,
        updated_at=at,
    )
    db.add(row)
    return row


@pytest.mark.asyncio
async def test_an_interrupted_event_is_recovered_once_it_has_waited(session):
    # Only this test's events: rows another test left in the table would be picked up
    # too. Deleted inside this test's transaction, which is rolled back, so they come back.
    await session.execute(delete(WebhookEvent))
    stuck = _event(session, minutes_ago=30)  # stored, never processed, no error
    failed = _event(session, minutes_ago=30, error="boom")
    in_flight = _event(session, minutes_ago=1)  # its own background task may still run
    _event(session, minutes_ago=30, processed=True)
    # Older than the lookback: one never attempted (the service was down for days)
    # is still recovered; one that failed and was retried has had its chances.
    days_ago = 60 * 24 * 5
    never_attempted = _event(session, minutes_ago=days_ago)
    gave_up = _event(session, minutes_ago=days_ago, error="boom", retries=1)
    await session.flush()

    @asynccontextmanager
    async def context():
        yield session

    retried = []

    async def retry(self, event_id):
        retried.append(event_id)
        return {"success": True}

    with (
        patch.object(task, "get_async_db_context", context),
        patch.object(task.WebhookMonitoringService, "retry_webhook", retry),
    ):
        stats = await task.run_webhook_reprocessing_task()

    assert set(retried) == {stuck.id, failed.id, never_attempted.id}
    assert in_flight.id not in retried
    assert gave_up.id not in retried
    assert stats["succeeded"] == 3
