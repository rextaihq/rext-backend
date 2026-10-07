"""
Integration test for the payment failure webhook handler (F11, revnix/rext-control#336).

A failed renewal makes the subscription PAST_DUE while Lemon Squeezy retries the
payment, and the plan stays; there is no grace deadline of our own. The handler
records when the failure episode began, keeps that date through later failures,
and returns the email to send once the transaction commits.

The tables it needs are created inside a transaction that is rolled back, so the
test runs the same on an empty test database and on a migrated one.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.webhook_handlers.subscription_handlers import handle_subscription_payment_failed
from tests.conftest import TEST_DATABASE_URL
from tests.db_tables import create_tables_unless_migrated


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: create_tables_unless_migrated(
                sync,
                [
                    Users,
                    SubscriptionPlan,
                    UserSubscription,
                    WebhookEvent,
                    WorkspaceModel,  # audit_logs refers to it
                    AuditLog,  # the handler records the failed payment
                ],
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _subscription(db, *, user=True, status=SubscriptionStatus.ACTIVE, failed_at=None):
    """A Pro subscription, its plan and (unless `user=False`) its user."""
    plan = SubscriptionPlan(
        name=f"pro-{uuid4().hex[:8]}",
        display_name="Pro Plan",
        price_monthly=29.99,
        price_yearly=299.99,
    )
    db.add(plan)
    owner = Users(email=f"{uuid4().hex[:12]}@example.com", full_name="Test User")
    if user:
        db.add(owner)
    await db.flush()
    subscription = UserSubscription(
        user_id=owner.id if user else uuid4(),
        plan_id=plan.id,
        status=status,
        billing_period=BillingPeriod.MONTHLY,
        start_date=datetime.now(timezone.utc) - timedelta(days=30),
        lemonsqueezy_subscription_id=f"sub_{uuid4().hex[:8]}",
        lemonsqueezy_customer_id="cus_12345",
        lemonsqueezy_variant_id="var_monthly",
        payment_failed_at=failed_at,
    )
    db.add(subscription)
    event = WebhookEvent(
        event_id=f"evt_{uuid4().hex[:8]}",
        event_name="subscription_payment_failed",
        payload={},
        processed=False,
    )
    db.add(event)
    await db.flush()
    return subscription, owner, event


def _payment_failed(subscription: UserSubscription, event: WebhookEvent) -> dict:
    """Lemon Squeezy's subscription_payment_failed, as the webhook processor passes it on."""
    return {
        "event_id": event.event_id,
        "event_type": "subscription_payment_failed",
        "data": {
            "type": "subscriptions",
            "id": subscription.lemonsqueezy_subscription_id,
            "attributes": {
                "status": "past_due",
                "customer_id": "cus_12345",
                "variant_id": "var_monthly",
                "first_subscription_item": {"price": 2999},
            },
        },
        "meta": {"custom_data": {}},
    }


@pytest.mark.asyncio
async def test_payment_failure_makes_the_subscription_past_due_and_keeps_the_plan(db_session):
    subscription, user, event = await _subscription(db_session)
    before = datetime.now(timezone.utc)

    email = await handle_subscription_payment_failed(
        _payment_failed(subscription, event), event, db_session
    )

    await db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.PAST_DUE
    assert subscription.plan_id is not None
    # No deadline of our own: access ends when Lemon Squeezy's retries run out.
    assert subscription.grace_period_end is None
    assert subscription.payment_failed_at >= before
    # The email goes out after the commit, with what the charge was for.
    assert email["send_email"] is True
    assert email["email_type"] == "payment_failed"
    assert email["email_data"]["user_id"] == str(user.id)
    assert email["email_data"]["user_email"] == user.email
    assert email["email_data"]["plan_name"] == "Pro Plan"
    assert email["email_data"]["amount_cents"] == 2999


@pytest.mark.asyncio
async def test_payment_failure_preserves_first_failure_timestamp(db_session):
    """A later failure in the same episode keeps the date the episode began."""
    first_failure = datetime.now(timezone.utc) - timedelta(days=2)
    subscription, _, event = await _subscription(
        db_session, status=SubscriptionStatus.PAST_DUE, failed_at=first_failure
    )

    await handle_subscription_payment_failed(
        _payment_failed(subscription, event), event, db_session
    )

    await db_session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.PAST_DUE
    assert subscription.payment_failed_at == first_failure


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED, SubscriptionStatus.UNPAID],
)
async def test_payment_failure_never_reopens_an_ended_subscription(db_session, status):
    subscription, _, event = await _subscription(db_session, status=status)

    email = await handle_subscription_payment_failed(
        _payment_failed(subscription, event), event, db_session
    )

    await db_session.refresh(subscription)
    assert subscription.status == status
    assert email is None


class _Rows:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


@pytest.mark.asyncio
async def test_payment_failure_for_a_missing_user_is_refused():
    """A subscription whose user can't be read is reported, not changed.

    The database can't hold one (user_id cascades on delete), so a stand-in session
    answers the two reads: the subscription, then no user.
    """
    subscription = UserSubscription(
        user_id=uuid4(),
        plan_id=uuid4(),
        status=SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
        lemonsqueezy_subscription_id="sub_orphan",
    )
    event = WebhookEvent(event_id="evt_orphan", event_name="subscription_payment_failed")
    db = AsyncMock()
    db.execute.side_effect = [_Rows(subscription), _Rows(None)]

    with pytest.raises(ValueError, match="not found"):
        await handle_subscription_payment_failed(_payment_failed(subscription, event), event, db)

    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.payment_failed_at is None
    db.flush.assert_not_called()
