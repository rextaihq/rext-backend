"""A handler's failure is recorded even though the rollback expired the event's row.

process_recorded rolls its transaction back before _mark_failed writes the failure
from its own session; the rollback expires every instance, and reading an expired
attribute is a query async code can't make. Checked on the test PostgreSQL, every
session on one connection whose transaction is rolled back at the end.
"""

import json
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.lemonsqueezy_webhook_service as service_module
from src.api.database.base import Base
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.lemonsqueezy_webhook_service import (
    LemonSqueezyWebhookService,
    WebhookProcessingError,
)
from tests.conftest import TEST_DATABASE_URL


@pytest_asyncio.fixture
async def connection():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[WebhookEvent.__table__], checkfirst=True
            )
        )
        yield conn
        await transaction.rollback()
    await engine.dispose()


def _session(conn):
    # A rollback inside the test returns to the session's savepoint, not further.
    return AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")


@pytest.mark.asyncio
async def test_a_failed_handler_is_recorded_after_the_rollback(connection, monkeypatch):
    async with _session(connection) as setup:
        setup.add(
            WebhookEvent(
                event_id="wh-rollback",
                event_name="subscription_updated",
                payload=json.loads('{"meta": {}, "data": {"id": "ls-1", "attributes": {}}}'),
                processed=False,
                retry_count=0,
            )
        )
        await setup.commit()

    @asynccontextmanager
    async def bookkeeping_session():
        async with _session(connection) as db:
            yield db

    monkeypatch.setattr(service_module, "AsyncSessionLocal", bookkeeping_session)

    async def failing_handler(*_):
        raise RuntimeError("the handler failed")

    async with _session(connection) as db:
        service = LemonSqueezyWebhookService(db)
        service._route_event = failing_handler
        with pytest.raises(WebhookProcessingError, match="the handler failed"):
            await service.process_recorded("wh-rollback")

    async with _session(connection) as check:
        row = (
            await check.execute(select(WebhookEvent).where(WebhookEvent.event_id == "wh-rollback"))
        ).scalar_one()
    assert row.processed is False
    assert row.retry_count == 1
    assert "the handler failed" in row.error_message
