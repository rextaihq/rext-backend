"""A refund request reads its order's own subscription (G37, revnix/rext-control#366).

The refund figures come from the subscription the order belongs to whenever it
still grants access (the app's access rule, `subscription_grants_access`); only
otherwise do they fall back to the user's newest subscription that does. Until
now the check compared the status with upper-case strings, never matched, and
always fell back, so a user with two subscriptions could be judged on the wrong
one.

The access rule is a SQL filter, so this runs on the test PostgreSQL: the tables
are created inside a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.services.refund_request_service import RefundRequestService
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    Users.__table__,
                    SubscriptionPlan.__table__,
                    UserSubscription.__table__,
                    Promotion.__table__,  # the refund figures count spent bonus credits
                    CreditGrant.__table__,
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _two_subscriptions(db, order_status, *, order_end=None):
    """The order's subscription (300 of 1,000 credits left) and a newer active one (900 left)."""
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
    ordered = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=order_status,
        end_date=order_end,
        current_credits=300,
        start_date=NOW - timedelta(days=20),
    )
    newer = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_credits=900,
        start_date=NOW - timedelta(days=2),
    )
    db.add_all([ordered, newer])
    await db.flush()
    order = SimpleNamespace(
        subscription_id=ordered.id,
        user_id=user.id,
        total=8900,
        lemonsqueezy_order_id=f"order-{uuid4().hex[:8]}",
        ordered_at=NOW - timedelta(days=20),
        created_at=NOW - timedelta(days=20),
    )
    return order


@pytest.mark.parametrize(
    ("status", "end"),
    [
        (SubscriptionStatus.ACTIVE, None),
        (SubscriptionStatus.PAST_DUE, None),  # Lemon Squeezy still retrying: the plan stays
        (SubscriptionStatus.CANCELLED, NOW + timedelta(days=5)),  # paid through
    ],
)
async def test_the_orders_own_subscription_is_used_while_it_grants_access(session, status, end):
    order = await _two_subscriptions(session, status, order_end=end)

    usage = await RefundRequestService(session)._get_credit_usage_details(order)

    # 700 of the order's subscription's 1,000 credits are used, not the newer one's 100.
    assert (usage["used"], usage["unused"]) == (700, 300)


@pytest.mark.parametrize(
    ("status", "end"),
    [
        (SubscriptionStatus.CANCELLED, NOW - timedelta(days=1)),  # its paid period is over
        (
            SubscriptionStatus.EXPIRED,
            NOW + timedelta(days=5),
        ),  # an end date does not bring access back
    ],
)
async def test_without_access_it_falls_back_to_the_newest_that_has_it(session, status, end):
    order = await _two_subscriptions(session, status, order_end=end)

    usage = await RefundRequestService(session)._get_credit_usage_details(order)

    assert (usage["used"], usage["unused"]) == (100, 900)
