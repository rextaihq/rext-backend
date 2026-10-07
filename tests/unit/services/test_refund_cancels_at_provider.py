"""A full refund ends the subscription at Lemon Squeezy too, and nothing revives it.

F8c, revnix/rext-control#538. Checked on the test PostgreSQL inside a rolled-back
transaction, with Lemon Squeezy, the refund records and the alerts replaced by mocks.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.refund_cancellation as module
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


async def _active_subscription(db) -> UserSubscription:
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
        end_date=NOW + timedelta(days=30),
        provider_updated_at=NOW - timedelta(days=1),
    )
    db.add(row)
    await db.flush()
    return row


def _event(row: UserSubscription, status: str, minutes_later: int = 5) -> dict:
    return {
        "data": {
            "type": "subscriptions",
            "id": row.lemonsqueezy_subscription_id,
            "attributes": {
                "status": status,
                "ends_at": (NOW + timedelta(days=30)).isoformat(),
                "renews_at": (NOW + timedelta(days=30)).isoformat(),
                "updated_at": (NOW + timedelta(minutes=minutes_later)).isoformat(),
            },
        }
    }


@pytest.mark.asyncio
async def test_a_full_refund_cancels_at_lemon_squeezy_once_and_ends_here(session, alerts):
    row = await _active_subscription(session)
    provider = SimpleNamespace(cancel_subscription=AsyncMock())

    await module.cancel_at_provider_for_refund(row, order_id="ord-1", provider=provider)
    module.end_for_refund(row, order_id="ord-1")
    # Run again (a second full-refund path, a replay): no second cancel.
    await module.cancel_at_provider_for_refund(row, order_id="ord-1", provider=provider)

    provider.cancel_subscription.assert_awaited_once_with(row.lemonsqueezy_subscription_id)
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.end_date <= datetime.now(timezone.utc)
    assert row.cancel_at_period_end is False
    assert row.provider_updated_at >= NOW
    record = row.subscription_metadata[module.ENDED_BY_REFUND]
    assert record["order_id"] == "ord-1" and record["provider_cancelled_at"]
    assert module.is_ended_by_refund(row)
    alerts.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_cancel_alerts_a_person_and_is_not_retried(session, alerts):
    row = await _active_subscription(session)
    provider = SimpleNamespace(cancel_subscription=AsyncMock(side_effect=RuntimeError("503")))

    await module.cancel_at_provider_for_refund(row, order_id="ord-2", provider=provider)
    module.end_for_refund(row, order_id="ord-2")
    await module.cancel_at_provider_for_refund(row, order_id="ord-2", provider=provider)

    provider.cancel_subscription.assert_awaited_once()
    assert alerts.call_count == 1
    assert alerts.call_args.kwargs["severity"] == "critical"
    assert "cancel it there by hand" in alerts.call_args.kwargs["message"]
    # The refund isn't undone, and access ends here all the same.
    assert row.subscription_metadata[module.ENDED_BY_REFUND]["provider_cancel_failed"]
    assert row.status == SubscriptionStatus.CANCELLED


@pytest.mark.asyncio
async def test_lemon_squeezys_later_updates_dont_bring_access_back(session, alerts, monkeypatch):
    """Its grace-period cancel says ends_at in a month; a refunded plan gives nothing."""
    import src.services.webhook_handlers.subscription_handlers as handlers

    handler_alerts = MagicMock()
    monkeypatch.setattr(handlers, "trigger_payment_alert", handler_alerts)
    row = await _active_subscription(session)
    module.end_for_refund(row, order_id="ord-3")
    await session.flush()
    ended = row.end_date

    for handler, status in (
        (handlers.handle_subscription_cancelled, "cancelled"),
        (handlers.handle_subscription_updated, "cancelled"),
    ):
        await handler(_event(row, status), SimpleNamespace(id=uuid4()), session)
    await session.refresh(row)
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.end_date == ended
    handler_alerts.assert_not_called()

    # Still active at Lemon Squeezy (its cancel failed, or someone resumed it there):
    # access stays ended here, and a person is told it can bill again.
    await handlers.handle_subscription_updated(
        _event(row, "active", minutes_later=10), SimpleNamespace(id=uuid4()), session
    )
    await handlers.handle_subscription_resumed(
        _event(row, "active", minutes_later=11), SimpleNamespace(id=uuid4()), session
    )
    await session.refresh(row)
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.end_date == ended
    assert handler_alerts.call_count == 2
    assert handler_alerts.call_args.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_a_refunded_subscription_is_never_offered_back(session, alerts):
    row = await _active_subscription(session)
    module.end_for_refund(row, order_id="ord-4")
    # Even with an end still in the future, as Lemon Squeezy's own cancel would set it.
    row.end_date = NOW + timedelta(days=20)
    assert billing_action(row) is None


@pytest.mark.asyncio
async def test_the_admin_refund_cancels_at_lemon_squeezy_on_a_full_refund_only(
    session, alerts, monkeypatch
):
    import src.api.routes.subscriptions.admin.refund_routes as routes

    row = await _active_subscription(session)
    provider = SimpleNamespace(
        get_refund=AsyncMock(return_value={"attributes": {"total": 3900, "refunded_amount": 0}}),
        create_refund=AsyncMock(return_value={"id": "rf-1", "attributes": {"refunded_amount": 0}}),
        cancel_subscription=AsyncMock(),
    )
    monkeypatch.setattr(routes, "get_lemonsqueezy_provider", AsyncMock(return_value=provider))
    orders = MagicMock()
    orders.get_by_lemonsqueezy_id = AsyncMock(return_value=None)
    monkeypatch.setattr(routes, "OrderService", MagicMock(return_value=orders))
    refunds = MagicMock()
    refunds.record_provider_refund = AsyncMock(return_value=None)
    monkeypatch.setattr(routes, "RefundService", MagicMock(return_value=refunds))
    usage = MagicMock()
    usage.reconcile_partial_refund_credits = AsyncMock(return_value=None)
    monkeypatch.setattr(routes, "UsageTrackingService", MagicMock(return_value=usage))

    # A partial refund keeps the subscription, here and at Lemon Squeezy.
    provider.create_refund.return_value = {"id": "rf-1", "attributes": {"refunded_amount": 1000}}
    refunds.get_refunded_total = AsyncMock(return_value=1000)
    await routes._issue_refund(
        session,
        lemonsqueezy_order_id="ord-5",
        user_id=row.user_id,
        subscription_id=row.id,
        amount=1000,
        reason="partial",
    )
    provider.cancel_subscription.assert_not_awaited()
    assert row.status == SubscriptionStatus.ACTIVE

    # The rest, a full refund now: cancelled at Lemon Squeezy and ended here.
    provider.get_refund.return_value = {"attributes": {"total": 3900, "refunded_amount": 1000}}
    provider.create_refund.return_value = {"id": "rf-2", "attributes": {"refunded_amount": 3900}}
    refunds.get_refunded_total = AsyncMock(return_value=3900)
    await routes._issue_refund(
        session,
        lemonsqueezy_order_id="ord-5",
        user_id=row.user_id,
        subscription_id=row.id,
        amount=None,
        reason="the rest",
    )
    provider.cancel_subscription.assert_awaited_once_with(row.lemonsqueezy_subscription_id)
    assert row.status == SubscriptionStatus.CANCELLED
    assert module.is_ended_by_refund(row)
