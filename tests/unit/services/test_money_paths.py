"""The money paths, end to end (F8, rext-control #270).

Each path is a sequence of Lemon Squeezy webhook events, given to the real handlers as Lemon Squeezy
sends them, on the test PostgreSQL. The tables are created inside a transaction that is rolled back,
so nothing is left behind. No test reaches Lemon Squeezy, an email provider or any other network.
The handlers return their emails as tasks rather than sending them, so nothing needs stubbing for
that.

The paths are ordered by what the 2026-10-08 launch changes: the launch offer, the refund rule,
a failed payment and its recovery, webhook replay, then the rest.
"""

import hashlib
import hmac
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.lemonsqueezy_webhook_service as webhook_service_module
from scripts.seeds.seed_promotions import LAUNCH_PROMOTION
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.discount_usage import DiscountUsage
from src.api.models.subscription_models.orders import Order
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.refund_requests import RefundRequest
from src.api.models.subscription_models.refunds import Refund
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.trial_conversions import TrialConversion
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.lemonsqueezy_webhook_service import (
    LemonSqueezyWebhookService,
    WebhookVerificationError,
)
from src.services.refund_request_service import RefundRequestError, RefundRequestService
from src.services.usage_tracking_service import UsageTrackingService
from src.services.webhook_handlers import register_default_handlers
from src.services.webhook_handlers.order_handlers import handle_order_created
from src.services.webhook_handlers.subscription_handlers import (
    handle_subscription_created,
    handle_subscription_payment_failed,
    handle_subscription_payment_recovered,
    handle_subscription_payment_success,
    handle_subscription_updated,
)
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio

OPENS = LAUNCH_PROMOTION["starts_at"]  # 2026-10-08 07:00 UTC
CLOSES = LAUNCH_PROMOTION["ends_at"]  # 2026-10-15 06:59 UTC
BEFORE_LAUNCH = OPENS - timedelta(days=2)


TABLES = [
    Users,
    SubscriptionPlan,
    UserSubscription,
    Promotion,
    CreditGrant,
    WorkspaceModel,  # audit_logs refers to it
    AuditLog,
    TrialConversion,
    Order,
    Refund,
    RefundRequest,
    DiscountUsage,
    WebhookEvent,
]


@pytest_asyncio.fixture
async def connection():
    """One connection whose transaction is rolled back at the end: nothing is left behind."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[t.__table__ for t in TABLES], checkfirst=True
            )
        )
        yield conn
        await transaction.rollback()
    await engine.dispose()


def _session(conn):
    # A commit or a rollback inside the code under test stops at the session's savepoint.
    return AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")


@pytest_asyncio.fixture
async def db(connection):
    async with _session(connection) as session:
        yield session


# --- the world: plans, a customer, the launch promotion ----------------------------


async def _plan(db, name, *, price, credits, trial=False):
    tag = uuid4().hex[:8]
    plan = SubscriptionPlan(
        name=f"{name}-{tag}",
        display_name=name.title(),
        price_monthly=price,
        price_yearly=price * 10,
        credits_per_month=credits,
        is_trial_plan=trial,
        lemonsqueezy_variant_id_monthly=None if trial else f"v-{name}-m-{tag}",
        lemonsqueezy_variant_id_yearly=None if trial else f"v-{name}-y-{tag}",
    )
    db.add(plan)
    await db.flush()
    return plan


async def _customer(db):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _launch_promotion(db):
    promotion = Promotion(id=uuid4(), **{**LAUNCH_PROMOTION, "code": f"launch-{uuid4().hex[:8]}"})
    db.add(promotion)
    await db.flush()
    return promotion


def _iso(moment: datetime) -> str:
    """A Lemon Squeezy timestamp: UTC with microseconds and a Z."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _meta(user, event_name=""):
    return {
        "event_name": event_name,
        "webhook_id": uuid4().hex,
        "custom_data": {"user_id": str(user.id)},
    }


def _subscription_event(
    user, ls_id, variant, *, at, status="active", order_id=None, name="subscription_created"
):
    return {
        "meta": _meta(user, name),
        "custom_data": {"user_id": str(user.id)},
        "data": {
            "type": "subscriptions",
            "id": str(ls_id),
            "attributes": {
                "status": status,
                "variant_id": variant,
                "customer_id": 4242,
                "user_email": user.email,
                "created_at": _iso(at),
                "updated_at": _iso(at),
                "renews_at": _iso(at + timedelta(days=30)),
                "ends_at": None,
                "trial_ends_at": None,
                "cancelled": False,
                "order_id": order_id,
            },
        },
    }


def _invoice_event(
    user,
    ls_id,
    *,
    at,
    billing_reason,
    total=8900,
    status="paid",
    name="subscription_payment_success",
):
    return {
        "meta": _meta(user, name),
        "custom_data": {"user_id": str(user.id)},
        "data": {
            "type": "subscription-invoices",
            "id": f"inv-{uuid4().hex[:8]}",
            "attributes": {
                "subscription_id": ls_id,
                "billing_reason": billing_reason,
                "status": status,
                "total": total,
                "created_at": _iso(at),
                "updated_at": _iso(at),
            },
        },
    }


def _order_event(user, order_id, variant, *, at, total=8900):
    return {
        "meta": _meta(user, "order_created"),
        "custom_data": {"user_id": str(user.id)},
        "data": {
            "type": "orders",
            "id": order_id,
            "attributes": {
                "status": "paid",
                "total": total,
                "subtotal": total,
                "tax": 0,
                "currency": "USD",
                "user_email": user.email,
                "customer_id": 4242,
                "refunded": False,
                "refunded_amount": 0,
                "created_at": _iso(at),
                "first_order_item": {
                    "variant_id": variant,
                    "product_id": "p-1",
                    "product_name": "Growth",
                },
                "urls": {"receipt": "https://example.invalid/receipt"},
            },
        },
    }


async def _subscription_of(db, ls_id) -> UserSubscription:
    result = await db.execute(
        select(UserSubscription).where(UserSubscription.lemonsqueezy_subscription_id == str(ls_id))
    )
    return result.scalar_one()


async def _grants(db, subscription) -> list[CreditGrant]:
    result = await db.execute(
        select(CreditGrant).where(CreditGrant.subscription_id == subscription.id)
    )
    return list(result.scalars().all())


# --- 1. the launch offer: double the first month's credits, from 2026-10-08 07:00 UTC ------


@pytest.mark.parametrize(
    ("started", "doubled"),
    [
        (OPENS - timedelta(seconds=1), False),  # one second before the launch
        (OPENS, True),  # the launch's first second
        (OPENS + timedelta(days=2), True),
        (CLOSES - timedelta(seconds=1), True),  # the week's last second
        (CLOSES, False),
    ],
)
async def test_launch_offer_doubles_a_paid_plan_started_in_its_window(db, started, doubled):
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9

    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started),
        None,
        db,
    )

    subscription = await _subscription_of(db, ls_id)
    grants = await _grants(db, subscription)
    assert subscription.current_credits == 1000
    assert [g.amount for g in grants] == ([1000] if doubled else [])
    if doubled:
        # The bonus lasts the first period, no longer than a month from the start.
        assert grants[0].expires_at <= started + timedelta(days=31)


async def test_launch_offer_is_granted_once_however_often_its_events_arrive(db):
    """The created event, its replay and the first invoice: one bonus."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS + timedelta(hours=3)
    created = _subscription_event(
        user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started, order_id="ord-launch-1"
    )

    await handle_subscription_created(created, None, db)
    await handle_subscription_created(created, None, db)  # the same event again
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=started + timedelta(minutes=1), billing_reason="initial"),
        None,
        db,
    )

    subscription = await _subscription_of(db, ls_id)
    assert [g.amount for g in await _grants(db, subscription)] == [1000]


async def test_a_trials_first_payment_gets_the_offer_when_it_started_in_the_window(db):
    """A paid plan's trial days, started in launch week, pays later: the bonus comes with
    the first payment, judged by when the subscription started."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS + timedelta(days=1)

    await handle_subscription_created(
        _subscription_event(
            user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started, status="on_trial"
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    assert await _grants(db, subscription) == []  # nothing until it is paid
    # start_date is when the event was processed; in launch week that is the event's own time.
    subscription.start_date = started
    await db.flush()

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=started + timedelta(days=7), billing_reason="initial"),
        None,
        db,
    )

    assert [g.amount for g in await _grants(db, subscription)] == [1000]


async def test_the_signup_trial_plan_gets_no_launch_bonus(db):
    from src.services.credit_grants import grant_promotion_bonus

    await _launch_promotion(db)
    trial = await _plan(db, "trial", price=0, credits=60, trial=True)
    user = await _customer(db)
    subscription = UserSubscription(
        user_id=user.id, plan_id=trial.id, status="TRIAL", current_credits=60
    )
    db.add(subscription)
    await db.flush()

    granted = await grant_promotion_bonus(
        db, subscription.id, trial, "monthly", OPENS + timedelta(hours=1), None
    )

    assert not granted
    assert await _grants(db, subscription) == []


# --- 2. the refund rule: within 14 days, under 100 credits used, the whole payment -----------


async def _paid_growth(db, *, ordered_days_ago=3):
    """A Growth subscriber whose first payment was some days ago (before the launch window,
    so no bonus muddies the counts)."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    order_id = f"ord-{uuid4().hex[:8]}"
    variant = growth.lemonsqueezy_variant_id_monthly
    await handle_subscription_created(
        _subscription_event(user, ls_id, variant, at=BEFORE_LAUNCH, order_id=order_id), None, db
    )
    paid_at = datetime.now(timezone.utc) - timedelta(days=ordered_days_ago)
    await handle_order_created(_order_event(user, order_id, variant, at=paid_at), None, db)
    await db.flush()
    return user, order_id


@pytest.mark.parametrize(("spent", "refundable"), [(0, True), (90, True), (105, False)])
async def test_a_refund_needs_fewer_than_100_credits_used(db, spent, refundable):
    user, order_id = await _paid_growth(db)
    if spent:
        assert await UsageTrackingService(db).consume_credits(user.id, spent)

    service = RefundRequestService(db)
    if refundable:
        request = await service.create_request(
            user_id=user.id, lemonsqueezy_order_id=order_id, reason="Not for me"
        )
        assert request.requested_amount == 8900  # the whole payment
    else:
        with pytest.raises(RefundRequestError, match="fewer than 100 credits"):
            await service.create_request(
                user_id=user.id, lemonsqueezy_order_id=order_id, reason="Not for me"
            )


async def test_a_refund_is_refused_after_14_days(db):
    user, order_id = await _paid_growth(db, ordered_days_ago=15)

    with pytest.raises(RefundRequestError, match="within 14 days"):
        await RefundRequestService(db).create_request(
            user_id=user.id, lemonsqueezy_order_id=order_id, reason="Too late"
        )


async def test_a_customers_refund_is_the_whole_payment_never_part(db):
    user, order_id = await _paid_growth(db)

    with pytest.raises(RefundRequestError, match="whole payment"):
        await RefundRequestService(db).create_request(
            user_id=user.id,
            lemonsqueezy_order_id=order_id,
            reason="Half, please",
            requested_amount=4000,
        )


# --- 3. a failed renewal: the plan stays while Lemon Squeezy retries, the month comes once --------


async def _active_growth(db, *, spend=0):
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = datetime.now(timezone.utc) - timedelta(days=30)
    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started),
        None,
        db,
    )
    if spend:
        assert await UsageTrackingService(db).consume_credits(user.id, spend)
    return user, ls_id, growth


async def test_a_failed_renewal_keeps_the_plan_and_its_balance_until_it_is_paid(db):
    user, ls_id, _ = await _active_growth(db, spend=300)
    usage = UsageTrackingService(db)
    now = datetime.now(timezone.utc)

    await handle_subscription_payment_failed(
        _invoice_event(
            user,
            ls_id,
            at=now - timedelta(hours=2),
            billing_reason="renewal",
            status="failed",
            name="subscription_payment_failed",
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    first_failure = subscription.payment_failed_at
    assert subscription.status.value == "past_due"
    assert await usage.get_credit_balance(user.id) == 700  # no new month while unpaid
    assert await usage.consume_credits(user.id, 15)  # still writing while it's retried

    await handle_subscription_payment_failed(
        _invoice_event(
            user,
            ls_id,
            at=now - timedelta(hours=1),
            billing_reason="renewal",
            status="failed",
            name="subscription_payment_failed",
        ),
        None,
        db,
    )
    assert (await _subscription_of(db, ls_id)).payment_failed_at == first_failure  # one episode

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now - timedelta(minutes=5), billing_reason="renewal"),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    assert subscription.status.value == "active"
    assert await usage.get_credit_balance(user.id) == 1000  # the new month, with the payment

    assert await usage.consume_credits(user.id, 100)
    await handle_subscription_payment_recovered(
        _invoice_event(
            user, ls_id, at=now, name="subscription_payment_recovered", billing_reason="renewal"
        ),
        None,
        db,
    )
    assert (await _subscription_of(db, ls_id)).status.value == "active"
    assert await usage.get_credit_balance(user.id) == 900  # "recovered" brings no second month


async def test_an_unpaid_renewal_stops_spending_until_it_is_paid(db):
    user, ls_id, growth = await _active_growth(db, spend=300)
    usage = UsageTrackingService(db)
    now = datetime.now(timezone.utc)

    await handle_subscription_updated(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(hours=1),
            status="unpaid",
            name="subscription_updated",
        ),
        None,
        db,
    )
    assert (await _subscription_of(db, ls_id)).status.value == "unpaid"
    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now, billing_reason="renewal"), None, db
    )
    assert (await _subscription_of(db, ls_id)).status.value == "active"
    assert await usage.get_credit_balance(user.id) == 1000
    assert await usage.consume_credits(user.id, 15)


# --- 4. webhook replay: Lemon Squeezy may send an event twice; it counts once ---------------------

SECRET = "test-webhook-secret"


def _signed(event: dict) -> tuple[bytes, str]:
    body = json.dumps(event).encode()
    return body, hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def service_sessions(connection, monkeypatch):
    """The service records events from sessions of its own: on the same connection."""

    @asynccontextmanager
    async def bookkeeping_session():
        async with _session(connection) as session:
            yield session

    monkeypatch.setattr(webhook_service_module, "AsyncSessionLocal", bookkeeping_session)


async def _service(db):
    service = LemonSqueezyWebhookService(db)
    register_default_handlers(service)
    service.webhook_secret = SECRET
    return service


async def test_a_replayed_renewal_does_not_refill_the_month(db, service_sessions):
    user, ls_id, _ = await _active_growth(db)
    await db.commit()
    renewal = _invoice_event(user, ls_id, at=datetime.now(timezone.utc), billing_reason="renewal")
    body, signature = _signed(renewal)
    usage = UsageTrackingService(db)

    first = await (await _service(db)).process_webhook(body, signature)
    assert first["success"] is True
    assert await usage.consume_credits(user.id, 300)
    assert await usage.get_credit_balance(user.id) == 700

    again = await (await _service(db)).process_webhook(body, signature)

    assert "duplicate" in again["message"].lower()
    assert await usage.get_credit_balance(user.id) == 700  # not refilled to 1000


async def test_an_event_with_a_wrong_signature_is_refused(db, service_sessions):
    user, ls_id, _ = await _active_growth(db, spend=300)
    body, _ = _signed(
        _invoice_event(user, ls_id, at=datetime.now(timezone.utc), billing_reason="renewal")
    )

    with pytest.raises(WebhookVerificationError):
        await (await _service(db)).process_webhook(body, "0" * 64)
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 700


# --- 5. the rest: plan changes, cancelling, refunds ------------------------------------------------


async def test_an_upgrade_and_a_downgrade_take_the_new_plans_credits_at_once(db):
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    await handle_subscription_created(
        _subscription_event(
            user, ls_id, starter.lemonsqueezy_variant_id_monthly, at=now - timedelta(days=3)
        ),
        None,
        db,
    )

    await handle_subscription_updated(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=2),
            name="subscription_updated",
        ),
        None,
        db,
    )
    upgraded = await _subscription_of(db, ls_id)
    assert upgraded.plan_id == growth.id
    assert upgraded.current_credits == 1000

    await handle_subscription_updated(
        _subscription_event(
            user,
            ls_id,
            starter.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=1),
            name="subscription_updated",
        ),
        None,
        db,
    )
    downgraded = await _subscription_of(db, ls_id)
    assert downgraded.plan_id == starter.id
    assert downgraded.current_credits <= 400


@pytest.mark.xfail(strict=True, reason="F8a rext-control#536: a plan change sets a full month")
async def test_switching_plans_down_and_up_does_not_refill_spent_credits(db):
    """Spend most of a month, switch to a smaller plan and back: the spent credits stay spent."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    await handle_subscription_created(
        _subscription_event(
            user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=now - timedelta(days=3)
        ),
        None,
        db,
    )
    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 900)  # 100 left of the month's 1,000

    for variant, hours_ago in (
        (starter.lemonsqueezy_variant_id_monthly, 2),
        (growth.lemonsqueezy_variant_id_monthly, 1),
    ):
        await handle_subscription_updated(
            _subscription_event(
                user,
                ls_id,
                variant,
                at=now - timedelta(hours=hours_ago),
                name="subscription_updated",
            ),
            None,
            db,
        )

    assert await usage.get_credit_balance(user.id) <= 100


async def test_a_cancelled_plan_keeps_access_until_its_end_then_expires(db):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_cancelled,
        handle_subscription_expired,
    )

    user, ls_id, growth = await _active_growth(db)
    usage = UsageTrackingService(db)
    now = datetime.now(timezone.utc)
    cancelled = _subscription_event(
        user,
        ls_id,
        growth.lemonsqueezy_variant_id_monthly,
        at=now - timedelta(minutes=10),
        status="cancelled",
        name="subscription_cancelled",
    )
    cancelled["data"]["attributes"]["cancelled"] = True
    cancelled["data"]["attributes"]["ends_at"] = _iso(now + timedelta(days=5))

    await handle_subscription_cancelled(cancelled, None, db)
    assert (await _subscription_of(db, ls_id)).status.value == "cancelled"
    assert await usage.consume_credits(user.id, 15)  # paid through: still writing

    expired = _subscription_event(
        user,
        ls_id,
        growth.lemonsqueezy_variant_id_monthly,
        at=now,
        status="expired",
        name="subscription_expired",
    )
    await handle_subscription_expired(expired, None, db)
    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False


def _refund_event(user, order_id, variant, *, total=8900):
    event = _order_event(user, order_id, variant, at=datetime.now(timezone.utc), total=total)
    event["meta"]["event_name"] = "order_refunded"
    event["data"]["attributes"].update(
        {"status": "refunded", "refunded": True, "refunded_amount": total}
    )
    return event


@pytest.fixture
def no_refund_mail(monkeypatch):
    from unittest.mock import AsyncMock

    import src.services.webhook_handlers.order_handlers as order_handlers

    monkeypatch.setattr(order_handlers, "send_billing_email_in_background", AsyncMock())


async def test_a_full_refund_of_the_first_payment_ends_access(db, no_refund_mail):
    from src.services.webhook_handlers.order_handlers import handle_order_refunded

    user, order_id = await _paid_growth(db)
    variant = (await db.execute(select(SubscriptionPlan))).scalars().first()

    await handle_order_refunded(
        _refund_event(user, order_id, variant.lemonsqueezy_variant_id_monthly), None, db
    )

    usage = UsageTrackingService(db)
    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False


@pytest.mark.xfail(strict=True, reason="F8b rext-control#537: a renewal order is not linked")
async def test_a_full_refund_of_a_renewal_ends_that_months_credits(db, no_refund_mail):
    """The refund rule covers any payment: refunding a renewal takes back that month."""
    from src.services.webhook_handlers.order_handlers import handle_order_refunded

    user, ls_id, growth = await _active_growth(db)
    variant = growth.lemonsqueezy_variant_id_monthly
    now = datetime.now(timezone.utc)
    renewal_order = f"ord-renewal-{uuid4().hex[:6]}"
    await handle_order_created(
        _order_event(user, renewal_order, variant, at=now - timedelta(days=1)), None, db
    )
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now - timedelta(days=1), billing_reason="renewal"),
        None,
        db,
    )
    usage = UsageTrackingService(db)
    assert await usage.get_credit_balance(user.id) == 1000

    await handle_order_refunded(_refund_event(user, renewal_order, variant), None, db)

    assert await usage.consume_credits(user.id, 15) is False


@pytest.mark.xfail(strict=True, reason="F8c rext-control#538: not cancelled at Lemon Squeezy")
async def test_a_refunded_plan_is_not_revived_by_lemon_squeezys_next_update(db, no_refund_mail):
    """After a full refund ends access, an "active" update without a new payment keeps it ended."""
    from src.services.webhook_handlers.order_handlers import handle_order_refunded

    user, order_id = await _paid_growth(db)
    plan = (await db.execute(select(SubscriptionPlan))).scalars().first()
    variant = plan.lemonsqueezy_variant_id_monthly
    subscription = (
        await db.execute(select(UserSubscription).where(UserSubscription.user_id == user.id))
    ).scalar_one()
    await handle_order_refunded(_refund_event(user, order_id, variant), None, db)

    await handle_subscription_updated(
        _subscription_event(
            user,
            subscription.lemonsqueezy_subscription_id,
            variant,
            at=datetime.now(timezone.utc) + timedelta(minutes=1),
            name="subscription_updated",
        ),
        None,
        db,
    )

    assert await UsageTrackingService(db).consume_credits(user.id, 15) is False


# --- 6. one subscription at a time (#831) ----------------------------------------------------------


async def test_no_second_checkout_while_a_renewal_is_past_due(db):
    """The customer fixes the card; a second subscription, which could be paid too, isn't opened."""
    from src.api.middleware.exceptions import DuplicateResourceException
    from src.api.models.subscription_models.subscriptions import BillingPeriod
    from src.services.subscription_service import UPDATE_PAYMENT_METHOD, SubscriptionService

    user, ls_id, growth = await _active_growth(db)
    await handle_subscription_payment_failed(
        _invoice_event(
            user,
            ls_id,
            at=datetime.now(timezone.utc),
            billing_reason="renewal",
            status="failed",
            name="subscription_payment_failed",
        ),
        None,
        db,
    )

    with pytest.raises(DuplicateResourceException) as refused:
        await SubscriptionService(db).create_checkout(
            user_id=user.id,
            plan_id=growth.id,
            billing_period=BillingPeriod.MONTHLY,
            success_url="https://app.example.invalid/ok",
            cancel_url="https://app.example.invalid/cancel",
        )
    assert refused.value.context["billing_action"] == UPDATE_PAYMENT_METHOD


async def test_resume_is_never_offered_for_an_old_cancellation_once_a_newer_plan_runs(db):
    """Resuming the old one would bill twice."""
    from src.services.subscription_service import RESUME, SubscriptionService, billing_action
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_cancelled

    user, old_id, growth = await _active_growth(db)
    now = datetime.now(timezone.utc)
    cancelled = _subscription_event(
        user,
        old_id,
        growth.lemonsqueezy_variant_id_monthly,
        at=now - timedelta(hours=2),
        status="cancelled",
        name="subscription_cancelled",
    )
    cancelled["data"]["attributes"]["cancelled"] = True
    cancelled["data"]["attributes"]["ends_at"] = _iso(now + timedelta(days=10))
    await handle_subscription_cancelled(cancelled, None, db)
    old = await _subscription_of(db, old_id)
    assert billing_action(old)["action"] == RESUME  # alone, it would be offered back

    new_id = uuid4().int % 10**9
    await handle_subscription_created(
        _subscription_event(
            user, new_id, growth.lemonsqueezy_variant_id_monthly, at=now - timedelta(hours=1)
        ),
        None,
        db,
    )

    assert await SubscriptionService(db).unfinished_subscription(user.id) is None
