"""A failed renewal keeps the plan through its grace period.

The access rule is a SQL filter, so it is checked on the test PostgreSQL: the
three tables it needs are created inside a transaction that is rolled back, so
nothing is left behind whatever the test database already holds.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.exceptions import DuplicateResourceException
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from src.services.subscription_service import SubscriptionService
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
LATER, EARLIER = NOW + timedelta(days=3), NOW - timedelta(days=1)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[Users.__table__, SubscriptionPlan.__table__, UserSubscription.__table__],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _subscription(db, status, *, grace=None, end=None, credits=600, reset=None):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}",
        display_name="Growth",
        price_monthly=89,
        price_yearly=890,
        credits_per_month=1000,
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        grace_period_end=grace,
        end_date=end,
        current_credits=credits,
        credits_reset_date=reset,
    )
    db.add(subscription)
    await db.flush()
    return user, plan, subscription


async def _grants(db, subscription) -> bool:
    found = await db.execute(
        select(UserSubscription.id).where(
            UserSubscription.id == subscription.id, subscription_grants_access(NOW)
        )
    )
    return found.scalar_one_or_none() is not None


@pytest.mark.parametrize(
    ("status", "grace", "end", "expected"),
    [
        (SubscriptionStatus.SUSPENDED, LATER, None, True),
        (SubscriptionStatus.SUSPENDED, EARLIER, None, False),
        (SubscriptionStatus.SUSPENDED, None, None, False),
        # Unchanged rules around it.
        (SubscriptionStatus.ACTIVE, None, None, True),
        (SubscriptionStatus.TRIAL, None, None, True),
        (SubscriptionStatus.CANCELLED, None, LATER, True),
        (SubscriptionStatus.CANCELLED, None, EARLIER, False),
        (SubscriptionStatus.EXPIRED, LATER, LATER, False),
    ],
)
@pytest.mark.asyncio
async def test_access_follows_the_grace_period(session, status, grace, end, expected):
    _, _, subscription = await _subscription(session, status, grace=grace, end=end)

    assert await _grants(session, subscription) is expected


@pytest.mark.asyncio
async def test_credits_endpoint_keeps_the_plan_during_the_grace_period(session):
    from src.api.server import app

    user, _, _ = await _subscription(session, SubscriptionStatus.SUSPENDED, grace=LATER)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/subscriptions/credits")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["current_credits"] == 600
    assert data["plan_name"] == "Growth"


@pytest.mark.parametrize(
    ("status", "balance_after"),
    [
        # The renewal failed at the reset date: no new month until the payment succeeds.
        (SubscriptionStatus.SUSPENDED, 600 - 15),
        # A paid subscription past its reset date is refilled first, as before.
        (SubscriptionStatus.ACTIVE, 1000 - 15),
    ],
)
@pytest.mark.asyncio
async def test_no_new_month_of_credits_while_a_payment_is_retried(session, status, balance_after):
    from src.services.usage_tracking_service import UsageTrackingService

    user, _, subscription = await _subscription(
        session, status, grace=LATER, reset=NOW - timedelta(hours=2)
    )

    assert await UsageTrackingService(session).consume_credits(user.id, 15) is True
    await session.refresh(subscription)
    assert subscription.current_credits == balance_after


@pytest.mark.asyncio
async def test_a_second_subscription_is_refused_while_a_payment_is_retried(monkeypatch):
    status = SubscriptionStatus.SUSPENDED
    service = SubscriptionService.__new__(SubscriptionService)
    monkeypatch.setattr(
        service,
        "get_subscription_by_user",
        lambda user_id: _awaitable(SimpleNamespace(status=status)),
        raising=False,
    )

    with pytest.raises(DuplicateResourceException) as subscribing:
        await service.subscribe(
            user_id=uuid4(), plan_id=uuid4(), billing_period=BillingPeriod.MONTHLY
        )
    with pytest.raises(DuplicateResourceException) as checking_out:
        await service.create_checkout(
            user_id=uuid4(),
            plan_id=uuid4(),
            billing_period=BillingPeriod.MONTHLY,
            success_url="https://app.example.com/ok",
            cancel_url="https://app.example.com/cancel",
        )

    for raised in (subscribing, checking_out):
        assert "Update your payment method" in raised.value.message


async def _awaitable(value):
    return value


def test_the_access_filter_names_only_statuses_the_database_holds():
    """The migrated subscriptionstatus type holds these names; past_due and paused are
    lowercase labels there (migration 33eb548e7bd9), so a query naming PAST_DUE or PAUSED
    fails on every real database even though a test database built from the models accepts it."""
    from sqlalchemy.dialects import postgresql

    sql = str(
        select(UserSubscription.id)
        .where(subscription_grants_access(NOW))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    assert "PAST_DUE" not in sql and "PAUSED" not in sql
    for name in ("ACTIVE", "TRIAL", "CANCELLED", "SUSPENDED"):
        assert f"'{name}'" in sql
