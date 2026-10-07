"""A refunded renewal ends that month's credits and access (F8b, revnix/rext-control#537).

Lemon Squeezy bills a renewal as a subscription invoice, and its refund arrives as
subscription_payment_refunded, which nothing handled. Checked on the test PostgreSQL
inside a rolled-back transaction, with Lemon Squeezy, the email and the alerts mocked.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.refund_cancellation as cancellation_module
import src.services.webhook_handlers.renewal_refund_handlers as module
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refunds import Refund
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.services.webhook_handlers import register_default_handlers
from src.services.webhook_handlers.subscription_handlers import (
    PAID_INVOICE_ID,
    _record_paid_invoice,
)
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
CREDITS = 400
PRICE = 3900


def _with_parents(*tables):
    found = []

    def visit(table):
        if table in found:
            return
        found.append(table)
        for key in table.foreign_keys:
            visit(key.column.table)

    for table in tables:
        visit(table)
    return found


@pytest_asyncio.fixture
async def session():
    tables = _with_parents(
        UserSubscription.__table__,
        Refund.__table__,
        Promotion.__table__,
        CreditGrant.__table__,
        AuditLog.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()

        def tables_unless_migrated(sync):
            if not inspect(sync).has_table("alembic_version"):
                Base.metadata.create_all(sync, tables=tables, checkfirst=True)

        await connection.run_sync(tables_unless_migrated)
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def outside(monkeypatch):
    """Lemon Squeezy, the refund email and the alerts."""
    provider = SimpleNamespace(cancel_subscription=AsyncMock())
    email = AsyncMock()
    alert = MagicMock()
    monkeypatch.setattr(module, "get_payment_provider", lambda: provider)
    monkeypatch.setattr(module, "send_billing_email_in_background", email)
    monkeypatch.setattr(module, "trigger_payment_alert", alert)
    monkeypatch.setattr(cancellation_module, "trigger_payment_alert", alert)
    return SimpleNamespace(provider=provider, email=email, alert=alert)


async def _renewed_subscription(db, paid_invoice: str = "inv-renewal") -> UserSubscription:
    """An active monthly plan whose latest renewal, invoice `paid_invoice`, was credited."""
    plan = SubscriptionPlan(
        name=f"starter-{uuid4().hex[:8]}", display_name="Starter", credits_per_month=CREDITS
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    row = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        start_date=NOW - timedelta(days=40),
        end_date=NOW + timedelta(days=25),
        current_credits=CREDITS,
        credits_reset_date=NOW + timedelta(days=25),
        provider_updated_at=NOW - timedelta(days=5),
    )
    _record_paid_invoice(row, NOW - timedelta(days=5), paid_invoice)
    db.add(row)
    await db.flush()
    return row


def _refund_event(
    row: UserSubscription,
    invoice: str = "inv-renewal",
    refunded: int = PRICE,
    billing_reason: str = "renewal",
) -> dict:
    return {
        "event_id": f"evt-{uuid4().hex[:8]}",
        "data": {
            "type": "subscription-invoices",
            "id": invoice,
            "attributes": {
                "subscription_id": row.lemonsqueezy_subscription_id,
                "billing_reason": billing_reason,
                "status": "refunded" if refunded >= PRICE else "partial_refund",
                "refunded": refunded >= PRICE,
                "refunded_amount": refunded,
                "refunded_at": NOW.isoformat(),
                "total": PRICE,
                "currency": "USD",
                "created_at": (NOW - timedelta(days=5)).isoformat(),
                "updated_at": NOW.isoformat(),
            },
        },
    }


async def _refunds(db, invoice: str) -> list[Refund]:
    key = module.invoice_refund_key(invoice)
    return list(
        (await db.execute(select(Refund).where(Refund.lemonsqueezy_order_id == key))).scalars()
    )


@pytest.mark.asyncio
async def test_a_full_refund_of_the_current_renewal_ends_the_month(session, outside):
    row = await _renewed_subscription(session)

    await module.handle_subscription_payment_refunded(_refund_event(row), None, session)

    refunds = await _refunds(session, "inv-renewal")
    assert [r.refund_amount for r in refunds] == [PRICE]
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.end_date <= datetime.now(timezone.utc)
    outside.provider.cancel_subscription.assert_awaited_once_with(row.lemonsqueezy_subscription_id)
    outside.email.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_replayed_refund_records_cancels_and_emails_nothing_more(session, outside):
    row = await _renewed_subscription(session)
    event = _refund_event(row)

    await module.handle_subscription_payment_refunded(event, None, session)
    await module.handle_subscription_payment_refunded(event, None, session)

    assert len(await _refunds(session, "inv-renewal")) == 1
    outside.provider.cancel_subscription.assert_awaited_once()
    outside.email.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_partial_refund_keeps_the_plan_and_shrinks_its_unused_credits(session, outside):
    row = await _renewed_subscription(session)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, refunded=PRICE // 2), None, session
    )

    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == CREDITS * (PRICE - PRICE // 2) // PRICE
    outside.provider.cancel_subscription.assert_not_awaited()
    assert [r.is_partial for r in await _refunds(session, "inv-renewal")] == [True]


@pytest.mark.asyncio
async def test_a_full_refund_of_an_earlier_payment_leaves_the_paid_period(session, outside):
    """A later renewal paid for the current period: it stays, and a person is told."""
    row = await _renewed_subscription(session, paid_invoice="inv-newer")

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-older"), None, session
    )

    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == CREDITS
    outside.provider.cancel_subscription.assert_not_awaited()
    assert len(await _refunds(session, "inv-older")) == 1
    outside.alert.assert_called_once()


@pytest.mark.asyncio
async def test_the_first_payment_is_left_to_its_orders_refund(session, outside):
    """order_refunded records the first payment's refund and ends the plan (F8c)."""
    row = await _renewed_subscription(session, paid_invoice="inv-initial")

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-initial", billing_reason="initial"), None, session
    )

    assert await _refunds(session, "inv-initial") == []
    assert row.status == SubscriptionStatus.ACTIVE
    outside.provider.cancel_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_invoice_of_no_known_subscription_alerts_and_changes_nothing(session, outside):
    row = await _renewed_subscription(session)
    event = _refund_event(row)
    event["data"]["attributes"]["subscription_id"] = "ls-unknown"

    await module.handle_subscription_payment_refunded(event, None, session)

    assert await _refunds(session, "inv-renewal") == []
    assert row.status == SubscriptionStatus.ACTIVE
    outside.alert.assert_called_once()


def test_a_payment_records_the_invoice_that_paid_the_period():
    row = UserSubscription(subscription_metadata={"other": 1})

    _record_paid_invoice(row, NOW, "inv-7")

    assert row.subscription_metadata[PAID_INVOICE_ID] == "inv-7"
    assert row.subscription_metadata["other"] == 1


def test_the_webhook_routes_a_refunded_renewal_to_its_handler():
    service = SimpleNamespace(handlers={})
    service.register_handler = lambda name, handler: service.handlers.__setitem__(name, handler)

    register_default_handlers(service)

    assert (
        service.handlers["subscription_payment_refunded"]
        is module.handle_subscription_payment_refunded
    )
