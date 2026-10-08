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
from sqlalchemy import event, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.refund_cancellation as cancellation_module
import src.services.webhook_handlers.renewal_refund_handlers as module
import src.services.webhook_handlers.subscription_handlers as subscription_handlers
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refunds import Refund
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.services.refund_service import RefundService
from src.services.webhook_handlers import register_default_handlers
from src.services.webhook_handlers.subscription_handlers import (
    PAID_INVOICE_ID,
    _last_paid_invoice_at,
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
        Order.__table__,
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


async def _renewed_subscription(
    db,
    paid_invoice: str = "inv-renewal",
    *,
    paid_at: datetime = NOW - timedelta(days=5),
    user_id=None,
    order_id: str | None = None,
    started: datetime = NOW - timedelta(days=40),
) -> UserSubscription:
    """An active monthly plan whose latest payment, invoice `paid_invoice`, was credited."""
    plan = SubscriptionPlan(
        name=f"starter-{uuid4().hex[:8]}", display_name="Starter", credits_per_month=CREDITS
    )
    db.add(plan)
    if user_id is None:
        user = Users(email=f"{uuid4().hex[:12]}@example.com")
        db.add(user)
        await db.flush()
        user_id = user.id
    await db.flush()
    row = UserSubscription(
        user_id=user_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        lemonsqueezy_order_id=order_id,
        start_date=started,
        end_date=NOW + timedelta(days=25),
        current_credits=CREDITS,
        credits_reset_date=NOW + timedelta(days=25),
        provider_updated_at=NOW - timedelta(days=5),
    )
    _record_paid_invoice(row, paid_at, paid_invoice)
    db.add(row)
    await db.flush()
    return row


def _refund_event(
    row: UserSubscription,
    invoice: str = "inv-renewal",
    refunded: int = PRICE,
    billing_reason: str = "renewal",
    created_at: datetime = NOW - timedelta(days=5),
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
                "created_at": created_at.isoformat(),
                "updated_at": NOW.isoformat(),
            },
        },
    }


def _payment_event(row: UserSubscription, invoice: str, created_at: datetime) -> dict:
    """subscription_payment_success for `invoice`, paid now."""
    return {
        "event_id": f"evt-{uuid4().hex[:8]}",
        "data": {
            "type": "subscription-invoices",
            "id": invoice,
            "attributes": {
                "subscription_id": row.lemonsqueezy_subscription_id,
                "billing_reason": "renewal",
                "status": "paid",
                "total": PRICE,
                "currency": "USD",
                "created_at": created_at.isoformat(),
                "updated_at": NOW.isoformat(),
            },
        },
    }


async def _refunds(db, invoice: str, *, key: str | None = None) -> list[Refund]:
    key = key or module.invoice_refund_key(invoice)
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
async def test_a_first_payment_refunded_without_its_order_event_is_recorded_and_ends(
    session, outside
):
    """Refunded through the invoice, the first payment brings no order_refunded: this event
    records it under the order's id and ends the plan, as F8c would."""
    row = await _renewed_subscription(session, paid_invoice="inv-initial", order_id="ord-1")

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-initial", billing_reason="initial"), None, session
    )

    assert [r.refund_amount for r in await _refunds(session, "", key="ord-1")] == [PRICE]
    assert await _refunds(session, "inv-initial") == []
    assert row.status == SubscriptionStatus.CANCELLED
    outside.provider.cancel_subscription.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_first_payment_and_its_order_refund_are_recorded_once(session, outside):
    """Refunded through the order, both events come: the shared key records it once."""
    row = await _renewed_subscription(session, paid_invoice="inv-initial", order_id="ord-2")

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-initial", billing_reason="initial"), None, session
    )
    # order_refunded records against the same order id and finds nothing new.
    again = await RefundService(session).record_provider_refund(
        lemonsqueezy_order_id="ord-2",
        user_id=row.user_id,
        provider_refunded_total=PRICE,
        original_amount=PRICE,
        subscription_id=row.id,
        reason="Order refunded via Lemon Squeezy",
    )

    assert again is None
    assert len(await _refunds(session, "", key="ord-2")) == 1
    outside.email.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_first_payment_on_a_row_without_its_orders_id_is_recorded_under_the_order(
    session, outside
):
    # An older row doesn't name its order. order_refunded records under the order's id, so
    # this event finds the same one through the order recorded for the subscription.
    row = await _renewed_subscription(session, paid_invoice="inv-initial")
    session.add(
        Order(
            user_id=row.user_id,
            subscription_id=row.id,
            lemonsqueezy_order_id="ord-older",
            total=PRICE,
        )
    )
    await session.flush()

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-initial", billing_reason="initial"), None, session
    )

    assert [r.refund_amount for r in await _refunds(session, "", key="ord-older")] == [PRICE]
    assert await _refunds(session, "inv-initial") == []


@pytest.mark.asyncio
async def test_the_refunds_lock_is_taken_before_the_subscriptions_row(session, outside):
    # order_refunded records (the refund's lock) and writes the subscription after. Taken
    # in the other order here, the two handlers of one first-payment refund would each
    # hold what the other waits for.
    row = await _renewed_subscription(session, paid_invoice="inv-initial", order_id="ord-3")
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    connection = session.bind.sync_connection
    event.listen(connection, "before_cursor_execute", record)
    try:
        await module.handle_subscription_payment_refunded(
            _refund_event(row, invoice="inv-initial", billing_reason="initial"), None, session
        )
    finally:
        event.remove(connection, "before_cursor_execute", record)

    lock = next(i for i, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql)
    row_lock = next(
        i for i, sql in enumerate(statements) if "user_subscriptions" in sql and "FOR UPDATE" in sql
    )
    assert lock < row_lock


@pytest.mark.asyncio
async def test_a_refunded_plan_change_invoice_is_recorded_and_left_to_a_person(session, outside):
    """A plan change's prorated invoice: its period stays paid, and its credits came with the
    change, so the plan isn't ended or cut."""
    row = await _renewed_subscription(session)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-upgrade", billing_reason="updated"), None, session
    )

    assert len(await _refunds(session, "inv-upgrade")) == 1
    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == CREDITS
    outside.provider.cancel_subscription.assert_not_awaited()
    assert outside.alert.call_args.kwargs["alert_type"] == "refund_of_plan_change"


@pytest.mark.asyncio
async def test_a_full_refund_that_comes_before_its_payment_still_ends_the_plan(session, outside):
    """The newest invoice, refunded before its payment_success was processed."""
    row = await _renewed_subscription(
        session, paid_invoice="inv-previous", paid_at=NOW - timedelta(days=30)
    )

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-new", created_at=NOW - timedelta(hours=1)), None, session
    )

    assert row.status == SubscriptionStatus.CANCELLED
    outside.provider.cancel_subscription.assert_awaited_once()
    outside.alert.assert_not_called()


@pytest.mark.asyncio
async def test_a_partial_refund_before_its_payment_cuts_the_month_once_it_is_granted(
    session, outside, monkeypatch
):
    row = await _renewed_subscription(
        session, paid_invoice="inv-previous", paid_at=NOW - timedelta(days=30)
    )
    row.current_credits = 25  # what was left of the previous month
    new = NOW - timedelta(hours=1)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-new", refunded=PRICE // 2, created_at=new), None, session
    )
    # Nothing to cut yet: the balance is the previous month's.
    assert row.current_credits == 25
    assert [r.is_partial for r in await _refunds(session, "inv-new")] == [True]

    monkeypatch.setattr(subscription_handlers, "_stamp_card_details", lambda *a: None)
    await subscription_handlers.handle_subscription_payment_success(
        _payment_event(row, "inv-new", new), None, session
    )

    assert row.current_credits == CREDITS * (PRICE - PRICE // 2) // PRICE
    # The cut is audited, as it is when the refund comes after its payment.
    audited = (
        (await session.execute(select(AuditLog).where(AuditLog.user_id == row.user_id)))
        .scalars()
        .all()
    )
    assert any(
        (entry.audit_metadata or {}).get("lemonsqueezy_invoice_id") == "inv-new"
        and "received before its payment" in str(entry.audit_metadata)
        for entry in audited
    )


def _credited_before_invoice_ids(row: UserSubscription) -> None:
    """A row whose last payment was credited before invoice ids were recorded."""
    row.subscription_metadata = {
        k: v for k, v in row.subscription_metadata.items() if k != PAID_INVOICE_ID
    }


@pytest.mark.asyncio
async def test_a_refund_ahead_of_its_payment_is_not_taken_for_the_month_before_on_an_older_row(
    session, outside
):
    row = await _renewed_subscription(
        session, paid_invoice="inv-previous", paid_at=NOW - timedelta(days=30)
    )
    _credited_before_invoice_ids(row)
    row.current_credits = 25  # what was left of the previous month

    await module.handle_subscription_payment_refunded(
        _refund_event(
            row, invoice="inv-new", refunded=PRICE // 2, created_at=NOW - timedelta(hours=1)
        ),
        None,
        session,
    )

    # Newer than the payment credited: it waits for its own payment, as on any other row.
    assert row.current_credits == 25
    assert row.subscription_metadata[module.EARLY_REFUND_INVOICE] == "inv-new"


@pytest.mark.asyncio
async def test_an_older_rows_credited_payment_is_still_the_current_one(session, outside):
    row = await _renewed_subscription(session)
    _credited_before_invoice_ids(row)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, refunded=PRICE // 2), None, session
    )

    assert row.current_credits == CREDITS * (PRICE - PRICE // 2) // PRICE


@pytest.mark.asyncio
async def test_a_partial_refund_cuts_the_refunded_subscriptions_credits_not_a_newer_ones(
    session, outside
):
    older = await _renewed_subscription(session, started=NOW - timedelta(days=90))
    newer = await _renewed_subscription(
        session, paid_invoice="inv-other", user_id=older.user_id, started=NOW - timedelta(days=3)
    )

    await module.handle_subscription_payment_refunded(
        _refund_event(older, refunded=PRICE // 2), None, session
    )

    assert older.current_credits == CREDITS * (PRICE - PRICE // 2) // PRICE
    assert newer.current_credits == CREDITS


@pytest.mark.asyncio
async def test_a_refund_before_its_subscription_exists_alerts_and_is_retried(session, outside):
    # subscription_created delayed, or failed and waiting for its retry: marked
    # processed, the refund would be lost and the plan granted in full afterwards.
    row = await _renewed_subscription(session)
    event = _refund_event(row)
    event["data"]["attributes"]["subscription_id"] = "ls-unknown"

    with pytest.raises(ValueError, match="retried once it has been created"):
        await module.handle_subscription_payment_refunded(event, None, session)

    assert await _refunds(session, "inv-renewal") == []
    assert row.status == SubscriptionStatus.ACTIVE
    outside.alert.assert_called_once()


@pytest.mark.asyncio
async def test_an_invoice_that_names_no_subscription_alerts_and_is_not_retried(session, outside):
    # Nothing to wait for: no later event can match it.
    row = await _renewed_subscription(session)
    event = _refund_event(row)
    del event["data"]["attributes"]["subscription_id"]

    await module.handle_subscription_payment_refunded(event, None, session)

    assert await _refunds(session, "inv-renewal") == []
    assert row.status == SubscriptionStatus.ACTIVE
    outside.alert.assert_called_once()


@pytest.mark.asyncio
async def test_a_plan_changes_payment_does_not_become_the_periods_invoice(
    session, outside, monkeypatch
):
    # The renewal paid for the period; an upgrade's prorated invoice was paid after it.
    # A refund of the renewal is still a refund of the current period's payment.
    row = await _renewed_subscription(session)
    monkeypatch.setattr(subscription_handlers, "_stamp_card_details", lambda *a: None)
    change = _payment_event(row, "inv-plan-change", NOW - timedelta(hours=2))
    change["data"]["attributes"]["billing_reason"] = "updated"

    await subscription_handlers.handle_subscription_payment_success(change, None, session)

    assert row.subscription_metadata[PAID_INVOICE_ID] == "inv-renewal"
    # Its time still orders the payments: an older one delivered late is ignored.
    assert _last_paid_invoice_at(row) == NOW

    await module.handle_subscription_payment_refunded(_refund_event(row), None, session)

    assert row.status == SubscriptionStatus.CANCELLED
    outside.provider.cancel_subscription.assert_awaited_once()


async def _trial_ended_by_a_plan_change(session, monkeypatch) -> UserSubscription:
    """A trial whose plan was changed in the app: Lemon Squeezy bills the first month with an
    invoice it labels "updated", and that payment has been processed."""
    row = await _renewed_subscription(session, started=NOW - timedelta(days=3))
    row.status = SubscriptionStatus.TRIAL
    row.trial_end_date = NOW + timedelta(days=4)
    row.current_credits = 40
    row.subscription_metadata = {}
    await session.flush()
    monkeypatch.setattr(subscription_handlers, "_stamp_card_details", lambda *a: None)
    first = _payment_event(row, "inv-first", NOW - timedelta(hours=2))
    first["data"]["attributes"]["billing_reason"] = "updated"
    await subscription_handlers.handle_subscription_payment_success(first, None, session)
    return row


@pytest.mark.asyncio
async def test_the_updated_invoice_that_ends_a_trial_is_the_periods_payment(
    session, outside, monkeypatch
):
    row = await _trial_ended_by_a_plan_change(session, monkeypatch)

    # It brought the month, so it is the invoice a refund of the period is measured against.
    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == CREDITS
    assert row.subscription_metadata[PAID_INVOICE_ID] == "inv-first"


@pytest.mark.asyncio
async def test_a_full_refund_of_the_invoice_that_ended_a_trial_ends_the_plan(
    session, outside, monkeypatch
):
    """Its label says plan change; it is the first payment, and its refund ends the plan as
    any first payment's does instead of being left to a person."""
    row = await _trial_ended_by_a_plan_change(session, monkeypatch)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-first", billing_reason="updated"), None, session
    )

    assert [r.refund_amount for r in await _refunds(session, "inv-first")] == [PRICE]
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.end_date <= datetime.now(timezone.utc)
    outside.provider.cancel_subscription.assert_awaited_once_with(row.lemonsqueezy_subscription_id)


@pytest.mark.asyncio
async def test_a_partial_refund_of_the_invoice_that_ended_a_trial_shrinks_the_month(
    session, outside, monkeypatch
):
    row = await _trial_ended_by_a_plan_change(session, monkeypatch)

    await module.handle_subscription_payment_refunded(
        _refund_event(row, invoice="inv-first", billing_reason="updated", refunded=PRICE // 2),
        None,
        session,
    )

    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == CREDITS * (PRICE - PRICE // 2) // PRICE
    outside.provider.cancel_subscription.assert_not_awaited()


@pytest.mark.asyncio
async def test_recording_a_refund_holds_the_orders_lock_until_the_transaction_ends(session):
    # Two events for one refund (a first payment's order_refunded and
    # subscription_payment_refunded) run in their own transactions. The second waits on
    # this lock, then reads the first one's row and records nothing.
    row = await _renewed_subscription(session)
    held = text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
        " AND ((classid::bigint << 32) | objid::bigint) = hashtextextended(:key, 0)"
    )
    assert (await session.execute(held, {"key": "refund:order-1"})).scalar_one() == 0

    await RefundService(session).record_provider_refund(
        lemonsqueezy_order_id="order-1",
        user_id=row.user_id,
        provider_refunded_total=PRICE,
        original_amount=PRICE,
        subscription_id=row.id,
    )

    assert (await session.execute(held, {"key": "refund:order-1"})).scalar_one() == 1
    assert (await session.execute(held, {"key": "refund:order-2"})).scalar_one() == 0


def test_the_invoice_refund_handler_uses_the_shared_provider():
    # One Lemon Squeezy provider, and so one HTTP client, for this refund path too.
    from src.providers.payment import provider_factory

    assert module.get_payment_provider is provider_factory.get_payment_provider_singleton


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
