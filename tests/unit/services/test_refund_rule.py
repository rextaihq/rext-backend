"""The refund rule (F7, revnix/rext-control#269; DECISIONS.md, founder).

Within 14 days of a payment, the whole payment comes back if fewer than 100
credits were used since it; no partial or pro-rata refunds. A customer's own
request follows it; an admin logging an emailed request reviews it instead and
may ask for part of a payment.

The request reads orders, refunds and subscriptions with SQL, so the create
tests run on the test PostgreSQL inside a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refund_requests import (
    REFUND_CREDIT_LIMIT,
    RefundRequest,
)
from src.api.models.subscription_models.refunds import Refund
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.api.schema.subscription.refund_schemas import RefundRequestCreate
from src.services.refund_request_service import (
    RefundRequestError,
    RefundRequestService,
    credit_rule_refusal,
)
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
GRANTED = 1000
TOTAL = 8900


@pytest.mark.parametrize(
    ("usage", "refused"),
    [
        ({"granted": GRANTED, "used": REFUND_CREDIT_LIMIT - 1}, False),
        ({"granted": GRANTED, "used": REFUND_CREDIT_LIMIT}, True),
        ({"granted": GRANTED, "used": 700}, True),
        ({"granted": 0, "used": 0}, False),  # a trial, or a plan without credits
    ],
)
def test_the_credit_rule_refuses_from_the_limit_up(usage, refused):
    refusal = credit_rule_refusal(usage)
    assert (refusal is not None) == refused
    if refused:
        assert str(REFUND_CREDIT_LIMIT) in refusal and str(usage["used"]) in refusal


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
                    Promotion.__table__,
                    CreditGrant.__table__,
                    Order.__table__,
                    Refund.__table__,
                    RefundRequest.__table__,
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _paid_order(db, *, used: int, days_ago: int = 2) -> Order:
    """A paid order of a 1,000-credit plan, `used` credits spent since."""
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}",
        display_name="Growth",
        price_monthly=89,
        price_yearly=890,
        credits_per_month=GRANTED,
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        current_credits=GRANTED - used,
        start_date=NOW - timedelta(days=days_ago),
    )
    db.add(subscription)
    await db.flush()
    order = Order(
        user_id=user.id,
        subscription_id=subscription.id,
        lemonsqueezy_order_id=f"order-{uuid4().hex[:8]}",
        total=TOTAL,
        currency="USD",
        status=OrderStatus.PAID,
        ordered_at=NOW - timedelta(days=days_ago),
    )
    db.add(order)
    await db.flush()
    return order


async def _request(db, order, **kwargs):
    return await RefundRequestService(db).create_request(
        user_id=order.user_id,
        lemonsqueezy_order_id=order.lemonsqueezy_order_id,
        reason="Not what I needed",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_under_the_limit_the_whole_payment_is_requested(session):
    order = await _paid_order(session, used=REFUND_CREDIT_LIMIT - 1)
    request = await _request(session, order)
    assert request.requested_amount == TOTAL


@pytest.mark.asyncio
async def test_at_the_limit_the_request_is_refused(session):
    order = await _paid_order(session, used=REFUND_CREDIT_LIMIT)
    with pytest.raises(RefundRequestError, match=f"fewer than {REFUND_CREDIT_LIMIT}"):
        await _request(session, order)


@pytest.mark.asyncio
async def test_a_customer_cannot_ask_for_part_of_a_payment(session):
    order = await _paid_order(session, used=10)
    with pytest.raises(RefundRequestError, match="whole payment"):
        await _request(session, order, requested_amount=1000)


@pytest.mark.asyncio
async def test_after_the_window_the_request_is_refused(session):
    order = await _paid_order(session, used=0, days_ago=15)
    with pytest.raises(RefundRequestError, match="within 14 days"):
        await _request(session, order)


@pytest.mark.asyncio
async def test_an_admin_logging_a_request_may_ask_for_part_past_the_rule(session):
    order = await _paid_order(session, used=700, days_ago=20)
    request = await _request(session, order, requested_amount=1000, enforce_policy=False)
    assert request.requested_amount == 1000


def test_the_customers_request_refuses_an_amount():
    # A client still sending the old partial amount is told so, not given the whole payment.
    with pytest.raises(ValidationError, match="requested_amount"):
        RefundRequestCreate(lemonsqueezy_order_id="1", reason="x", requested_amount=1000)
    assert RefundRequestCreate(lemonsqueezy_order_id="1", reason="x").reason == "x"
