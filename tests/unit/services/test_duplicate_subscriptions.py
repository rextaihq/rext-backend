"""Two live Lemon Squeezy subscriptions: the newer stays, the older is cancelled and refunded.

F11, revnix/rext-control#336. Checked on the test PostgreSQL inside a rolled-back
transaction, with Lemon Squeezy and the alert replaced by mocks.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.duplicate_subscriptions as module
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.subscription_service import billing_action
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
                    WorkspaceModel.__table__,
                    AuditLog.__table__,
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def alerts(monkeypatch):
    alert = MagicMock()
    monkeypatch.setattr(module, "trigger_payment_alert", alert)
    return alert


def _provider(invoice={"id": "inv-old", "total": 8900}, refund_error=None):
    return SimpleNamespace(
        cancel_subscription=AsyncMock(),
        latest_paid_invoice=AsyncMock(return_value=invoice),
        refund_subscription_invoice=AsyncMock(side_effect=refund_error),
    )


async def _customer_with(db, *statuses):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=1000
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    rows = []
    for days_ago, status in zip(range(len(statuses), 0, -1), statuses):
        row = UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=status,
            lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
            created_at=NOW - timedelta(days=days_ago),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return user, rows  # oldest first


@pytest.mark.asyncio
async def test_the_older_is_cancelled_and_refunded_and_we_are_told(session, alerts):
    user, (older, newer) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    provider = _provider()

    settled = await module.settle_duplicate_subscriptions(session, user.id, provider)

    assert settled == [older.id]
    provider.cancel_subscription.assert_awaited_once_with(older.lemonsqueezy_subscription_id)
    provider.refund_subscription_invoice.assert_awaited_once_with("inv-old", 8900)
    await session.refresh(older)
    await session.refresh(newer)
    assert older.status == SubscriptionStatus.CANCELLED
    assert older.subscription_metadata["duplicate_of"] == str(newer.id)
    assert older.subscription_metadata["duplicate_refunded_invoice_id"] == "inv-old"
    assert newer.status == SubscriptionStatus.ACTIVE
    assert alerts.call_args.kwargs["severity"] == "high"
    # A settled duplicate is never offered back as "resume".
    assert billing_action(older) is None


@pytest.mark.asyncio
async def test_a_settled_duplicate_is_not_settled_again(session, alerts):
    user, _ = await _customer_with(session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE)
    await module.settle_duplicate_subscriptions(session, user.id, _provider())
    again = _provider()

    assert await module.settle_duplicate_subscriptions(session, user.id, again) == []
    again.cancel_subscription.assert_not_called()
    again.refund_subscription_invoice.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_refund_asks_a_person_and_is_not_retried(session, alerts):
    user, (older, _) = await _customer_with(
        session, SubscriptionStatus.PAST_DUE, SubscriptionStatus.ACTIVE
    )

    settled = await module.settle_duplicate_subscriptions(
        session, user.id, _provider(refund_error=RuntimeError("refund refused"))
    )

    assert settled == [older.id]
    await session.refresh(older)
    assert (
        "refund its latest paid invoice" in older.subscription_metadata["duplicate_settle_failed"]
    )
    assert alerts.call_args.kwargs["severity"] == "critical"
    again = _provider()
    assert await module.settle_duplicate_subscriptions(session, user.id, again) == []
    again.refund_subscription_invoice.assert_not_called()


@pytest.mark.parametrize(
    "statuses",
    [
        (SubscriptionStatus.ACTIVE,),
        (SubscriptionStatus.EXPIRED, SubscriptionStatus.ACTIVE),
        (SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE),
    ],
)
@pytest.mark.asyncio
async def test_one_live_subscription_is_left_alone(session, alerts, statuses):
    user, _ = await _customer_with(session, *statuses)
    provider = _provider()

    assert await module.settle_duplicate_subscriptions(session, user.id, provider) == []
    provider.cancel_subscription.assert_not_called()
    alerts.assert_not_called()


@pytest.mark.asyncio
async def test_a_late_recovery_of_the_older_one_settles_it(session, alerts, monkeypatch):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_recovered,
    )

    user, (older, newer) = await _customer_with(
        session, SubscriptionStatus.UNPAID, SubscriptionStatus.ACTIVE
    )
    provider = _provider()
    monkeypatch.setattr(module, "get_payment_provider_singleton", lambda: provider)

    await handle_subscription_payment_recovered(
        {
            "data": {
                "type": "subscription-invoices",
                "id": "inv-late",
                "attributes": {
                    "subscription_id": older.lemonsqueezy_subscription_id,
                    "total": 8900,
                },
            }
        },
        SimpleNamespace(id=uuid4(), event_type="subscription_payment_recovered"),
        session,
    )

    rows = {
        row.id: row.status
        for row in (
            await session.scalars(
                select(UserSubscription).where(UserSubscription.user_id == user.id)
            )
        ).all()
    }
    assert rows == {older.id: SubscriptionStatus.CANCELLED, newer.id: SubscriptionStatus.ACTIVE}
    provider.refund_subscription_invoice.assert_awaited_once()
