"""Two live Lemon Squeezy subscriptions: the newer stays, the older is cancelled and refunded.

F11, revnix/rext-control#336. Checked on the test PostgreSQL inside a rolled-back
transaction, with Lemon Squeezy and the alert replaced by mocks. The cancel and the
refund run only with BILLING_AUTO_SETTLE_DUPLICATES=true (off by default, founder
2026-10-07): these tests turn it on, except the ones about it being off.
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


@pytest.fixture(autouse=True)
def auto_settle(monkeypatch):
    monkeypatch.setenv("BILLING_AUTO_SETTLE_DUPLICATES", "true")


@pytest.fixture
def alerts(monkeypatch):
    alert = MagicMock()
    monkeypatch.setattr(module, "trigger_payment_alert", alert)
    return alert


def _invoice(status="paid", total=8900, refunded=False, id="inv-old"):
    return {"id": id, "status": status, "total": total, "refunded": refunded}


def _provider(invoice=None, refund_error=None):
    return SimpleNamespace(
        cancel_subscription=AsyncMock(),
        latest_invoice=AsyncMock(return_value=invoice or _invoice()),
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
    assert "refund its latest invoice" in older.subscription_metadata["duplicate_settle_failed"]
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


@pytest.mark.asyncio
async def test_a_partly_refunded_invoice_goes_to_a_person_not_an_older_one(session, alerts):
    user, (older, _) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    provider = _provider(_invoice(status="partial_refund", refunded=True))

    assert await module.settle_duplicate_subscriptions(session, user.id, provider) == [older.id]

    provider.refund_subscription_invoice.assert_not_called()
    await session.refresh(older)
    assert "partial_refund" in older.subscription_metadata["duplicate_settle_failed"]
    assert older.status == SubscriptionStatus.CANCELLED
    assert alerts.call_args.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_a_refund_made_already_is_not_made_again(session, alerts):
    """An earlier attempt refunded, then its transaction didn't commit: the retry refunds nothing."""
    user, (older, _) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    provider = _provider(_invoice(status="refunded", refunded=True))

    await module.settle_duplicate_subscriptions(session, user.id, provider)

    provider.refund_subscription_invoice.assert_not_called()
    await session.refresh(older)
    assert older.subscription_metadata["duplicate_refunded_invoice_id"] == "inv-old"
    assert older.subscription_metadata["duplicate_refund_found_done"] is True
    assert "duplicate_settle_failed" not in older.subscription_metadata
    assert alerts.call_args.kwargs["severity"] == "high"


@pytest.mark.asyncio
async def test_the_newer_purchase_stays_whatever_order_the_webhooks_came_in(session, alerts):
    """Stored first but bought last: Lemon Squeezy's creation time decides, not ours."""
    user, (stored_first, stored_last) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    stored_first.subscription_metadata = module.provider_created_record("2026-10-06T10:00:00Z")
    stored_last.subscription_metadata = module.provider_created_record("2026-10-06T09:00:00Z")
    await session.flush()
    provider = _provider()

    assert await module.settle_duplicate_subscriptions(session, user.id, provider) == [
        stored_last.id
    ]
    provider.cancel_subscription.assert_awaited_once_with(stored_last.lemonsqueezy_subscription_id)
    assert stored_first.status == SubscriptionStatus.ACTIVE


@pytest.mark.asyncio
async def test_one_settlement_per_customer_at_a_time(session, alerts, monkeypatch):
    """The customer's lock comes before the read, so a second webhook waits and then sees both."""
    user, _ = await _customer_with(session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE)
    statements = []
    execute = session.execute

    async def recording(statement, *args, **kwargs):
        statements.append((str(statement), args[0] if args else None))
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", recording)

    await module.settle_duplicate_subscriptions(session, user.id, _provider())

    sql, params = statements[0]
    assert "pg_advisory_xact_lock" in sql
    assert params == {"key": f"subscriptions:settle:{user.id}"}


@pytest.mark.asyncio
async def test_a_settled_duplicate_keeps_its_end_when_lemon_squeezy_cancels_it(
    session, alerts, monkeypatch
):
    """Lemon Squeezy's cancellation says ends_at in a month; the refunded one gives no plan."""
    import src.services.webhook_handlers.subscription_handlers as handlers

    handler_alerts = MagicMock()
    monkeypatch.setattr(handlers, "trigger_payment_alert", handler_alerts)

    user, (older, _) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    await module.settle_duplicate_subscriptions(session, user.id, _provider())
    await session.refresh(older)
    ended = older.end_date

    def event(status):
        return {
            "data": {
                "type": "subscriptions",
                "id": older.lemonsqueezy_subscription_id,
                "attributes": {
                    "status": status,
                    "ends_at": (NOW + timedelta(days=30)).isoformat(),
                    "updated_at": (NOW + timedelta(minutes=1)).isoformat(),
                },
            }
        }

    await handlers.handle_subscription_cancelled(
        event("cancelled"), SimpleNamespace(id=uuid4()), session
    )
    await handlers.handle_subscription_updated(
        event("cancelled"), SimpleNamespace(id=uuid4()), session
    )
    await session.refresh(older)
    assert older.end_date == ended
    handler_alerts.assert_not_called()

    # Resumed in Lemon Squeezy's portal, it can bill again: a person is told.
    await handlers.handle_subscription_updated(
        event("active"), SimpleNamespace(id=uuid4()), session
    )
    await session.refresh(older)
    assert older.status == SubscriptionStatus.CANCELLED
    assert handler_alerts.call_args.kwargs["severity"] == "critical"


@pytest.mark.parametrize("setting", [None, "false"])
@pytest.mark.asyncio
async def test_while_automatic_settlement_is_off_a_person_is_asked_once(
    session, alerts, monkeypatch, setting
):
    """Off by default: nothing is cancelled or refunded, no access changes, one alert."""
    if setting is None:
        monkeypatch.delenv("BILLING_AUTO_SETTLE_DUPLICATES", raising=False)
    else:
        monkeypatch.setenv("BILLING_AUTO_SETTLE_DUPLICATES", setting)
    user, (older, newer) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    provider = _provider()

    assert await module.settle_duplicate_subscriptions(session, user.id, provider) == []
    assert await module.settle_duplicate_subscriptions(session, user.id, provider) == []

    provider.cancel_subscription.assert_not_called()
    provider.latest_invoice.assert_not_called()
    provider.refund_subscription_invoice.assert_not_called()
    await session.refresh(older)
    assert older.status == SubscriptionStatus.ACTIVE
    assert older.end_date is None
    assert older.subscription_metadata["duplicate_found_of"] == str(newer.id)
    assert "duplicate_of" not in older.subscription_metadata
    assert newer.status == SubscriptionStatus.ACTIVE
    assert alerts.call_count == 1
    assert alerts.call_args.kwargs["severity"] == "critical"
    # Once a person cancels it by hand, it isn't offered back as "resume" either.
    older.status = SubscriptionStatus.CANCELLED
    older.end_date = NOW + timedelta(days=20)
    assert billing_action(older) is None


# --- revnix/rext-control#529, part A: before automatic settlement is turned on ----------


@pytest.mark.asyncio
async def test_a_known_duplicate_grants_nothing(session, alerts):
    """Settled here or left to a person, a duplicate never gives the plan, even before its end."""
    from src.api.models.subscription_models.subscriptions import subscription_grants_access

    user, (found, settled, kept) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE
    )
    found.subscription_metadata = {"duplicate_found_of": str(kept.id)}
    settled.subscription_metadata = {"duplicate_of": str(kept.id)}
    settled.end_date = NOW + timedelta(days=25)  # Lemon Squeezy's paid-through end
    await session.flush()

    granting = (
        await session.scalars(
            select(UserSubscription.id).where(
                UserSubscription.user_id == user.id, subscription_grants_access()
            )
        )
    ).all()

    assert granting == [kept.id]


@pytest.mark.asyncio
async def test_a_late_recovery_on_a_settled_duplicate_changes_nothing_and_tells_a_person(
    session, alerts, monkeypatch
):
    import src.services.webhook_handlers.subscription_handlers as handlers

    handler_alerts = MagicMock()
    monkeypatch.setattr(handlers, "trigger_payment_alert", handler_alerts)
    user, (older, _) = await _customer_with(
        session, SubscriptionStatus.ACTIVE, SubscriptionStatus.ACTIVE
    )
    await module.settle_duplicate_subscriptions(session, user.id, _provider())
    await session.refresh(older)
    ended = older.end_date

    task = await handlers.handle_subscription_payment_recovered(
        {
            "data": {
                "type": "subscription-invoices",
                "id": "inv-again",
                "attributes": {
                    "subscription_id": older.lemonsqueezy_subscription_id,
                    "total": 8900,
                },
            }
        },
        SimpleNamespace(id=uuid4(), event_type="subscription_payment_recovered"),
        session,
    )

    await session.refresh(older)
    assert task is None
    assert older.status == SubscriptionStatus.CANCELLED
    assert older.end_date == ended
    assert handler_alerts.call_args.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_an_older_purchase_arriving_last_gets_no_bonus_audit_or_welcome(
    session, alerts, monkeypatch
):
    """Its subscription_created comes after the newer one's: it's settled on arrival, and that's all."""
    import src.services.webhook_handlers.subscription_handlers as handlers

    provider = _provider()
    monkeypatch.setattr(module, "get_payment_provider_singleton", lambda: provider)
    bonus = AsyncMock()
    monkeypatch.setattr(handlers, "grant_promotion_bonus", bonus)
    user, (newer,) = await _customer_with(session, SubscriptionStatus.ACTIVE)
    newer.subscription_metadata = module.provider_created_record("2026-10-06T10:00:00Z")
    plan = await session.get(SubscriptionPlan, newer.plan_id)
    plan.lemonsqueezy_variant_id_monthly = f"var-{uuid4().hex[:6]}"
    await session.flush()
    payload = {
        "data": {
            "type": "subscriptions",
            "id": "ls-bought-first",
            "attributes": {
                "status": "active",
                "variant_id": plan.lemonsqueezy_variant_id_monthly,
                "user_email": user.email,
                "created_at": "2026-10-06T09:00:00Z",
                "updated_at": "2026-10-06T09:00:05Z",
            },
        },
        "custom_data": {"user_id": str(user.id)},
    }

    task = await handlers.handle_subscription_created(
        payload, SimpleNamespace(id=uuid4(), event_type="subscription_created"), session
    )

    older = await session.scalar(
        select(UserSubscription).where(
            UserSubscription.lemonsqueezy_subscription_id == "ls-bought-first"
        )
    )
    assert task is None
    assert older.status == SubscriptionStatus.CANCELLED
    assert older.subscription_metadata["duplicate_of"] == str(newer.id)
    provider.cancel_subscription.assert_awaited_once_with("ls-bought-first")
    bonus.assert_not_called()
    created_audit = await session.execute(
        select(AuditLog.id).where(AuditLog.resource_id == str(older.id))
    )
    assert created_audit.first() is None


@pytest.mark.asyncio
async def test_an_older_purchase_left_to_a_person_gets_no_bonus_audit_or_welcome_either(
    session, alerts, monkeypatch
):
    """With automatic settlement off it is only marked, and stops there all the same."""
    import src.services.webhook_handlers.subscription_handlers as handlers

    monkeypatch.delenv("BILLING_AUTO_SETTLE_DUPLICATES", raising=False)
    bonus = AsyncMock()
    monkeypatch.setattr(handlers, "grant_promotion_bonus", bonus)
    user, (newer,) = await _customer_with(session, SubscriptionStatus.ACTIVE)
    newer.subscription_metadata = module.provider_created_record("2026-10-06T10:00:00Z")
    plan = await session.get(SubscriptionPlan, newer.plan_id)
    plan.lemonsqueezy_variant_id_monthly = f"var-{uuid4().hex[:6]}"
    await session.flush()
    payload = {
        "data": {
            "type": "subscriptions",
            "id": "ls-bought-first-manual",
            "attributes": {
                "status": "active",
                "variant_id": plan.lemonsqueezy_variant_id_monthly,
                "user_email": user.email,
                "created_at": "2026-10-06T09:00:00Z",
                "updated_at": "2026-10-06T09:00:05Z",
            },
        },
        "custom_data": {"user_id": str(user.id)},
    }

    task = await handlers.handle_subscription_created(
        payload, SimpleNamespace(id=uuid4(), event_type="subscription_created"), session
    )

    older = await session.scalar(
        select(UserSubscription).where(
            UserSubscription.lemonsqueezy_subscription_id == "ls-bought-first-manual"
        )
    )
    assert task is None
    assert older.status == SubscriptionStatus.ACTIVE  # a person cancels and refunds it
    assert older.subscription_metadata["duplicate_found_of"] == str(newer.id)
    bonus.assert_not_called()
    created_audit = await session.execute(
        select(AuditLog.id).where(AuditLog.resource_id == str(older.id))
    )
    assert created_audit.first() is None
