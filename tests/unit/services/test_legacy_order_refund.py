"""A full refund of an order with no local record still ends its subscription (F8c.2, #593).

Customers from before orders were recorded have no order row here, and their subscription
row has no lemonsqueezy_order_id. A full refund made in Lemon Squeezy's dashboard used to
return silently, leaving the subscription active there, to renew and charge again. Checked
on the test PostgreSQL inside a rolled-back transaction, with Lemon Squeezy mocked.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.refund_cancellation as cancellation_module
import src.services.webhook_handlers.order_handlers as module
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refunds import Refund
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
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
        Order.__table__,
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
def lemon(monkeypatch):
    """Lemon Squeezy, the refund email and the alerts; `subscriptions` maps an order to its ids."""
    provider = SimpleNamespace(
        cancel_subscription=AsyncMock(),
        subscription_ids_for_order=AsyncMock(return_value=[]),
    )
    alert = MagicMock()
    monkeypatch.setattr(module, "get_payment_provider", lambda: provider)
    monkeypatch.setattr(module, "send_billing_email_in_background", AsyncMock())
    monkeypatch.setattr(cancellation_module, "trigger_payment_alert", alert)
    return SimpleNamespace(provider=provider, alert=alert)


async def _legacy_subscription(db) -> UserSubscription:
    """An active plan from before order recording: no order row, no lemonsqueezy_order_id."""
    plan = SubscriptionPlan(
        name=f"starter-{uuid4().hex[:8]}", display_name="Starter", credits_per_month=400
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    row = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        end_date=NOW + timedelta(days=25),
        provider_updated_at=NOW - timedelta(days=5),
    )
    db.add(row)
    await db.flush()
    return row


def _refund_event(order_id: str, refunded: int = PRICE) -> dict:
    return {
        "event_id": f"evt-{uuid4().hex[:8]}",
        "data": {
            "type": "orders",
            "id": order_id,
            "attributes": {
                "customer_id": 4242,
                "status": "refunded" if refunded >= PRICE else "partial_refund",
                "refunded": refunded >= PRICE,
                "refunded_amount": refunded,
                "refunded_at": NOW.isoformat(),
                "total": PRICE,
                "currency": "USD",
                "first_order_item": {"variant_id": 1, "product_id": 2, "product_name": "Starter"},
            },
        },
    }


async def _refunds(db, order_id: str) -> list[Refund]:
    return list(
        (await db.execute(select(Refund).where(Refund.lemonsqueezy_order_id == order_id))).scalars()
    )


@pytest.mark.asyncio
async def test_a_legacy_full_refund_finds_its_subscription_through_lemon_squeezy(session, lemon):
    row = await _legacy_subscription(session)
    lemon.provider.subscription_ids_for_order.return_value = [row.lemonsqueezy_subscription_id]

    await module.handle_order_refunded(_refund_event("ord-legacy"), None, session)

    lemon.provider.subscription_ids_for_order.assert_awaited_once_with("ord-legacy")
    lemon.provider.cancel_subscription.assert_awaited_once_with(row.lemonsqueezy_subscription_id)
    assert row.status == SubscriptionStatus.CANCELLED
    assert [r.refund_amount for r in await _refunds(session, "ord-legacy")] == [PRICE]
    lemon.alert.assert_not_called()


async def _statements_of(db, payload: dict) -> list[str]:
    """The SQL handle_order_refunded runs for this event, in order."""
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_rest):
        statements.append(statement)

    connection = db.bind.sync_connection
    event.listen(connection, "before_cursor_execute", record)
    try:
        await module.handle_order_refunded(payload, None, db)
    finally:
        event.remove(connection, "before_cursor_execute", record)
    return statements


@pytest.mark.asyncio
async def test_the_refunds_lock_is_taken_before_the_orders_row_is_written(session, lemon):
    # The admin's refund takes the refund's lock and then writes the order's row. Written
    # first here, each would hold what the other waits for, and the request the database
    # then ends could be the admin's, after Lemon Squeezy returned the money.
    row = await _legacy_subscription(session)
    session.add(
        Order(
            user_id=row.user_id,
            subscription_id=row.id,
            lemonsqueezy_order_id="ord-known",
            total=PRICE,
        )
    )
    await session.flush()

    statements = await _statements_of(session, _refund_event("ord-known"))

    lock = next(i for i, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql)
    write = next(i for i, sql in enumerate(statements) if sql.startswith("UPDATE orders"))
    assert lock < write
    assert [r.refund_amount for r in await _refunds(session, "ord-known")] == [PRICE]


@pytest.mark.asyncio
async def test_the_refunds_lock_is_taken_before_a_legacy_subscriptions_row(session, lemon):
    # The same for the subscription's row, which this lookup locks and the admin's refund
    # writes after the refund's lock.
    row = await _legacy_subscription(session)
    lemon.provider.subscription_ids_for_order.return_value = [row.lemonsqueezy_subscription_id]

    statements = await _statements_of(session, _refund_event("ord-legacy-lock"))

    lock = next(i for i, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql)
    row_lock = next(
        i for i, sql in enumerate(statements) if "user_subscriptions" in sql and "FOR UPDATE" in sql
    )
    assert lock < row_lock


@pytest.mark.asyncio
async def test_a_full_refund_found_nowhere_alerts_a_person_once(session, lemon):
    await module.handle_order_refunded(_refund_event("ord-nowhere"), None, session)

    lemon.alert.assert_called_once()
    assert lemon.alert.call_args.kwargs["severity"] == "critical"
    assert "ord-nowhere" in lemon.alert.call_args.kwargs["message"]
    assert await _refunds(session, "ord-nowhere") == []


@pytest.mark.asyncio
async def test_a_lookup_that_fails_counts_as_not_found(session, lemon):
    lemon.provider.subscription_ids_for_order.side_effect = RuntimeError("503")

    await module.handle_order_refunded(_refund_event("ord-down"), None, session)

    lemon.alert.assert_called_once()


@pytest.mark.asyncio
async def test_a_partial_refund_found_nowhere_alerts_no_one(session, lemon):
    """Access stays on a partial refund, so there is nothing to cancel."""
    await module.handle_order_refunded(
        _refund_event("ord-part", refunded=PRICE // 2), None, session
    )

    lemon.alert.assert_not_called()
