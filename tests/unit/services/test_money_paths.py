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
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.api.models.subscription_models.subscriptions as subscriptions_module
import src.services.credit_grants as credit_grants_module
import src.services.lemonsqueezy_webhook_service as webhook_service_module
import src.services.refund_request_service as refund_request_module
import src.services.subscription_service as subscription_service_module
import src.services.usage_tracking_service as usage_module
import src.services.webhook_handlers.subscription_handlers as subscription_handlers_module
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
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.subscription_models.trial_conversions import TrialConversion
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.refund_request_service import RefundRequestError, RefundRequestService
from src.services.subscription_service import SubscriptionService
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
        # A migrated test database holds the real launch offer. Only the promotions a test
        # makes itself count here, or a test that reads the real clock would get the bonus
        # while the suite runs in launch week.
        await session.execute(update(Promotion).values(is_active=False))
        yield session


@pytest.fixture
def clock(monkeypatch):
    """The time the handlers and the credit services read, set by the test.

    The launch offer's paths are judged against a fixed week, so a test that reads the real
    clock would change its outcome while the suite runs inside that week, and again once the
    bonus has expired.
    """
    current = {}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            moment = current["now"]
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    for module in (
        subscription_handlers_module,
        credit_grants_module,
        usage_module,
        subscriptions_module,
        refund_request_module,
    ):
        monkeypatch.setattr(module, "datetime", Clock)

    def set_to(moment: datetime) -> None:
        current["now"] = moment

    return set_to


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
    user,
    ls_id,
    variant,
    *,
    at,
    status="active",
    order_id=None,
    name="subscription_created",
    renews_at=None,
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
                # A plan change keeps the period: Lemon Squeezy's renews_at stays.
                "renews_at": _iso(renews_at or at + timedelta(days=30)),
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
        # The bonus lasts the first period: it ends with it (renews_at, 30 days here),
        # which comes before a calendar month from the start.
        assert grants[0].expires_at == started + timedelta(days=30)


async def test_launch_offer_is_granted_once_however_often_its_events_arrive(db, clock):
    """The created event, its replay and the first invoice: one bonus."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS + timedelta(hours=3)
    clock(started + timedelta(minutes=5))
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
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 2000


async def test_credits_spent_between_the_starts_events_stay_spent(db, clock):
    """Spend after the subscription was created, then its first invoice and the created event
    arrive again (Lemon Squeezy's order isn't guaranteed, and a failed delivery is retried):
    neither gives back what was spent."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS + timedelta(hours=3)
    clock(started + timedelta(minutes=5))
    created = _subscription_event(
        user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started, order_id="ord-launch-2"
    )
    await handle_subscription_created(created, None, db)
    usage = UsageTrackingService(db)
    # 1,200: the bonus's 1,000 first, then 200 of the month's 1,000.
    assert await usage.consume_credits(user.id, 1200)
    assert await usage.get_credit_balance(user.id) == 800

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=started + timedelta(minutes=1), billing_reason="initial"),
        None,
        db,
    )
    await handle_subscription_created(created, None, db)

    assert await usage.get_credit_balance(user.id) == 800


@pytest.mark.xfail(
    strict=True,
    reason="F8d rext-control#543: the first payment judges the window by the processing time",
)
async def test_a_trials_first_payment_gets_the_offer_when_it_started_in_the_window(db, clock):
    """A paid plan's trial days, started in launch week, pays later: the bonus comes with
    the first payment, judged by when Lemon Squeezy started the subscription (its created_at),
    not by when the event happened to be processed. Here it started in the week's last hour
    and its event was processed after the week (a retried delivery)."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = CLOSES - timedelta(hours=1)

    clock(CLOSES + timedelta(hours=1))
    await handle_subscription_created(
        _subscription_event(
            user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started, status="on_trial"
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    assert await _grants(db, subscription) == []  # nothing until it is paid

    paid = started + timedelta(days=7)
    clock(paid + timedelta(minutes=1))
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=paid, billing_reason="initial"),
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


# The offer holds a subscription that started inside its window or whose first payment falls
# inside it, whatever Lemon Squeezy calls that payment's invoice (F8f, rext-control #848).


async def _trial_started(db, clock, plan, *, started):
    """A paid plan's trial days, started at `started` and its event processed then."""
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    clock(started + timedelta(minutes=1))
    await handle_subscription_created(
        _subscription_event(
            user, ls_id, plan.lemonsqueezy_variant_id_monthly, at=started, status="on_trial"
        ),
        None,
        db,
    )
    return user, ls_id


async def _payment_records_begin(db, at=OPENS - timedelta(days=30)):
    """The audit log's first payment record, another customer's, made at `at`: a month before
    the launch unless a test says otherwise. The log vouches for subscriptions started after
    it, and for none while it is empty."""
    db.add(
        AuditLog(
            action="payment.succeeded",
            resource_type="payment",
            resource_id=str(uuid4()),
            created_at=at,
        )
    )
    await db.flush()


async def _pays(db, clock, user, ls_id, *, at, billing_reason):
    clock(at + timedelta(minutes=1))
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=at, billing_reason=billing_reason), None, db
    )


@pytest.mark.parametrize("billing_reason", ["initial", "updated", "renewal"])
async def test_a_trial_begun_before_the_offer_gets_the_bonus_when_it_first_pays_inside_it(
    db, clock, billing_reason
):
    """The trial began two days before the launch and pays in launch week. A plan change in
    the app ends a trial with an invoice labelled "updated": it is the first payment all the
    same, and brings the month and the bonus."""
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=BEFORE_LAUNCH)
    subscription = await _subscription_of(db, ls_id)
    assert await _grants(db, subscription) == []  # nothing until it is paid

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason=billing_reason)

    assert [g.amount for g in await _grants(db, subscription)] == [1000]
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 2000


@pytest.mark.parametrize("billing_reason", ["initial", "updated"])
async def test_a_trial_begun_inside_the_offer_gets_the_bonus_when_it_pays_after_it_closed(
    db, clock, billing_reason
):
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=CLOSES - timedelta(days=2))

    await _pays(
        db, clock, user, ls_id, at=CLOSES + timedelta(days=5), billing_reason=billing_reason
    )

    subscription = await _subscription_of(db, ls_id)
    assert [g.amount for g in await _grants(db, subscription)] == [1000]
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 2000


@pytest.mark.parametrize(
    ("started", "paid"),
    [
        (OPENS - timedelta(days=9), OPENS - timedelta(days=2)),  # all of it before the launch
        (CLOSES + timedelta(days=1), CLOSES + timedelta(days=8)),  # all of it after the week
        (OPENS - timedelta(days=3), CLOSES + timedelta(days=4)),  # around the week, never in it
    ],
)
@pytest.mark.parametrize("billing_reason", ["initial", "updated"])
async def test_a_trial_begun_and_first_paid_outside_the_offer_gets_no_bonus(
    db, clock, started, paid, billing_reason
):
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=started)

    await _pays(db, clock, user, ls_id, at=paid, billing_reason=billing_reason)

    subscription = await _subscription_of(db, ls_id)
    assert await _grants(db, subscription) == []
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 1000


@pytest.mark.parametrize("billing_reason", ["updated", "renewal"])
async def test_a_plan_paid_for_before_the_offer_gets_no_bonus_from_an_invoice_inside_it(
    db, clock, billing_reason
):
    """A subscriber from before the launch changes plan, or renews, in launch week: that
    payment is not their first, so the offer is not theirs."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    clock(BEFORE_LAUNCH + timedelta(minutes=1))
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=BEFORE_LAUNCH,
            order_id=f"ord-{uuid4().hex[:8]}",
        ),
        None,
        db,
    )

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason=billing_reason)

    subscription = await _subscription_of(db, ls_id)
    assert await _grants(db, subscription) == []


async def test_a_first_payment_under_another_name_gives_the_bonus_once(db, clock):
    """The trial's upgrade pays ("updated"); the same event arrives again, and later invoices
    of either name follow. One bonus, and what was spent stays spent."""
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=BEFORE_LAUNCH)
    paid = OPENS + timedelta(days=1)
    first = _invoice_event(user, ls_id, at=paid, billing_reason="updated")
    clock(paid + timedelta(minutes=1))
    await handle_subscription_payment_success(first, None, db)
    usage = UsageTrackingService(db)
    # 1,200: the bonus's 1,000 first, then 200 of the month's 1,000.
    assert await usage.consume_credits(user.id, 1200)

    await handle_subscription_payment_success(first, None, db)  # the same event again
    for minutes, again in enumerate(("initial", "updated"), 5):
        await _pays(
            db, clock, user, ls_id, at=paid + timedelta(minutes=minutes), billing_reason=again
        )

    subscription = await _subscription_of(db, ls_id)
    assert [g.amount for g in await _grants(db, subscription)] == [1000]
    assert await usage.get_credit_balance(user.id) == 800


def _as_from_before_the_records(subscription, status):
    """The row as one stored before the start-month marker and the credited payment existed."""
    subscription.status = status
    subscription.subscription_metadata = {
        k: v
        for k, v in subscription.subscription_metadata.items()
        if k not in ("start_month_given", "paid_invoice_at")
    }


async def test_a_renewal_recovered_inside_the_offer_is_no_first_payment(db, clock):
    """A subscriber from before the records who was behind on a renewal when they began: the
    row says unpaid and holds no payment, exactly as a first payment that failed does. The
    payment in the audit log tells them apart, and this one gets its month and no bonus."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS - timedelta(days=40)
    clock(started + timedelta(minutes=1))
    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started),
        None,
        db,
    )
    await _pays(db, clock, user, ls_id, at=started + timedelta(minutes=2), billing_reason="initial")
    subscription = await _subscription_of(db, ls_id)
    _as_from_before_the_records(subscription, SubscriptionStatus.PAST_DUE)
    subscription.current_credits = 0
    await db.flush()

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason="renewal")

    paid = await _subscription_of(db, ls_id)
    assert paid.status == SubscriptionStatus.ACTIVE
    assert paid.current_credits == 1000
    assert await _grants(db, paid) == []


@pytest.mark.parametrize(
    ("billing_reason", "granted"), [("updated", []), ("renewal", []), ("initial", [1000])]
)
async def test_an_empty_payment_log_vouches_for_nobody(db, clock, billing_reason, granted):
    """No payment in the audit log at all: a new database, or one whose records have aged
    out. It cannot say that a subscription never paid, so a payment that is not called
    "initial" is not taken for a first one. One that is called "initial" still is."""
    await _launch_promotion(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=BEFORE_LAUNCH)

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason=billing_reason)

    subscription = await _subscription_of(db, ls_id)
    assert subscription.current_credits == 1000
    assert [g.amount for g in await _grants(db, subscription)] == granted


async def test_a_subscription_older_than_the_payment_records_is_not_taken_for_a_first_payment(
    db, clock
):
    """A subscriber who started before the audit log kept payments, behind on a renewal: the
    log holds no payment of theirs, but it could not: it began after they did. Its silence
    says nothing, so the payment is not taken for a first one."""
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    started = OPENS - timedelta(days=40)
    clock(started + timedelta(minutes=1))
    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=started),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    _as_from_before_the_records(subscription, SubscriptionStatus.PAST_DUE)
    subscription.current_credits = 0
    await db.flush()

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason="renewal")

    paid = await _subscription_of(db, ls_id)
    assert paid.current_credits == 1000
    assert await _grants(db, paid) == []


async def test_a_first_payment_that_had_failed_gets_the_bonus_when_paid_inside_the_offer(db, clock):
    """The other row that reads unpaid with no payment: a trial from before the records whose
    first payment failed. It started after the audit log began to keep payments and the log
    holds none of its own, so the payment that comes in launch week is its first."""
    await _launch_promotion(db)
    await _payment_records_begin(db)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user, ls_id = await _trial_started(db, clock, growth, started=BEFORE_LAUNCH)
    subscription = await _subscription_of(db, ls_id)
    _as_from_before_the_records(subscription, SubscriptionStatus.PAST_DUE)
    await db.flush()

    await _pays(db, clock, user, ls_id, at=OPENS + timedelta(days=1), billing_reason="renewal")

    paid = await _subscription_of(db, ls_id)
    assert paid.current_credits == 1000
    assert [g.amount for g in await _grants(db, paid)] == [1000]


# --- 2. the refund rule: within 14 days, under 100 credits used, the whole payment -----------


async def _paid_growth(db, *, ordered_days_ago=3, paid_at=None):
    """A Growth subscriber whose first payment was some days ago, or at `paid_at` (before the
    launch window, so no bonus muddies the counts)."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    order_id = f"ord-{uuid4().hex[:8]}"
    variant = growth.lemonsqueezy_variant_id_monthly
    await handle_subscription_created(
        _subscription_event(user, ls_id, variant, at=BEFORE_LAUNCH, order_id=order_id), None, db
    )
    paid_at = paid_at or datetime.now(timezone.utc) - timedelta(days=ordered_days_ago)
    await handle_order_created(_order_event(user, order_id, variant, at=paid_at), None, db)
    await db.flush()
    return user, order_id


@pytest.mark.parametrize(("spent", "refundable"), [(0, True), (99, True), (100, False)])
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


@pytest.mark.parametrize(
    ("age", "refundable"),
    [
        (timedelta(days=14), True),  # the window's last instant
        (timedelta(days=14, microseconds=1), False),  # the first instant past it
    ],
)
async def test_a_refund_is_open_for_exactly_14_days(db, clock, age, refundable):
    # A whole second, so the order's stored time is exact whatever precision it keeps.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    clock(now)
    user, order_id = await _paid_growth(db, paid_at=now - age)

    service = RefundRequestService(db)
    if refundable:
        request = await service.create_request(
            user_id=user.id, lemonsqueezy_order_id=order_id, reason="Just in time"
        )
        assert request.requested_amount == 8900
    else:
        with pytest.raises(RefundRequestError, match="within 14 days"):
            await service.create_request(
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
    return service


async def test_a_replayed_renewal_does_not_refill_the_month(db, service_sessions):
    """As the live route does it: verify, store (record_webhook), process (process_recorded)."""
    from src.utils.lemonsqueezy_webhook import verify_webhook_signature

    user, ls_id, _ = await _active_growth(db)
    await db.commit()
    body, signature = _signed(
        _invoice_event(user, ls_id, at=datetime.now(timezone.utc), billing_reason="renewal")
    )
    usage = UsageTrackingService(db)

    assert verify_webhook_signature(payload=body, signature=signature, secret=SECRET)
    recorded = await (await _service(db)).record_webhook(body)
    assert recorded["duplicate"] is False
    processed = await (await _service(db)).process_recorded(recorded["event_id"])
    assert processed["message"] == "Event processed successfully"
    assert await usage.consume_credits(user.id, 300)
    assert await usage.get_credit_balance(user.id) == 700

    again = await (await _service(db)).record_webhook(body)  # Lemon Squeezy sends it again
    assert again["duplicate"] is True  # the route answers "duplicate" and processes nothing
    once_more = await (await _service(db)).process_recorded(recorded["event_id"])
    assert once_more["message"] == "Nothing to process"
    assert await usage.get_credit_balance(user.id) == 700  # not refilled to 1000


def test_an_event_with_a_wrong_signature_is_refused():
    """The live route verifies first and answers 401 without storing anything."""
    from src.utils.lemonsqueezy_webhook import verify_webhook_signature

    body = json.dumps({"meta": {"event_name": "subscription_payment_success"}}).encode()
    good = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(payload=body, signature=good, secret=SECRET)
    assert not verify_webhook_signature(payload=body, signature="0" * 64, secret=SECRET)
    assert not verify_webhook_signature(payload=body + b" ", signature=good, secret=SECRET)


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
    assert downgraded.current_credits == 400  # nothing was spent


async def test_switching_plans_down_and_up_does_not_refill_spent_credits(db):
    """Spend most of a month, switch to a smaller plan and back: the spent credits stay spent
    (F8a, the founder's rule: the new plan's credits less those used this period)."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=27)
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=3),
            renews_at=period_end,
        ),
        None,
        db,
    )
    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 900)  # 100 left of the month's 1,000

    await _change_plan(db, user, ls_id, starter, at=now - timedelta(hours=2), period_end=period_end)
    assert await usage.get_credit_balance(user.id) == 0  # 900 used is more than Starter's 400
    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=1), period_end=period_end)

    assert await usage.get_credit_balance(user.id) == 100


async def _starter_spent(db, spend):
    """A Starter subscriber (400 a month) three days into the period, who has spent some."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=27)
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            starter.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=3),
            renews_at=period_end,
        ),
        None,
        db,
    )
    assert await UsageTrackingService(db).consume_credits(user.id, spend)
    return user, ls_id, starter, growth, now, period_end


async def _change_plan(db, user, ls_id, plan, *, at, period_end, status="active"):
    await handle_subscription_updated(
        _subscription_event(
            user,
            ls_id,
            plan.lemonsqueezy_variant_id_monthly,
            at=at,
            status=status,
            renews_at=period_end,
            name="subscription_updated",
        ),
        None,
        db,
    )


async def test_an_upgrade_adds_only_the_difference_paid_for(db):
    """300 of Starter's 400 used, then Growth: 1,000 less the 300 used."""
    user, ls_id, _, growth, now, period_end = await _starter_spent(db, 300)

    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=1), period_end=period_end)

    assert await UsageTrackingService(db).get_credit_balance(user.id) == 700


async def test_a_plan_changes_prorated_invoice_brings_no_new_month(db):
    """Lemon Squeezy charges the difference with billing_reason "updated": the change already
    set the credits, so the payment doesn't reset them to a full month."""
    user, ls_id, _, growth, now, period_end = await _starter_spent(db, 300)
    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=1), period_end=period_end)

    await handle_subscription_payment_success(
        _invoice_event(
            user, ls_id, at=now - timedelta(minutes=50), billing_reason="updated", total=3300
        ),
        None,
        db,
    )

    assert await UsageTrackingService(db).get_credit_balance(user.id) == 700


async def test_the_next_period_after_a_plan_change_starts_from_its_own_month(db):
    """The renewal brings the new plan's full month, and a change in that period counts only
    what was used in it."""
    user, ls_id, starter, growth, now, period_end = await _starter_spent(db, 300)
    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=3), period_end=period_end)
    usage = UsageTrackingService(db)

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now - timedelta(hours=2), billing_reason="renewal"),
        None,
        db,
    )
    assert await usage.get_credit_balance(user.id) == 1000

    assert await usage.consume_credits(user.id, 100)
    await _change_plan(
        db,
        user,
        ls_id,
        starter,
        at=now - timedelta(hours=1),
        period_end=period_end + timedelta(days=30),
    )
    assert await usage.get_credit_balance(user.id) == 300  # 400 less the 100 used this period


@pytest.mark.parametrize("billing_reason", ["initial", "updated"])
async def test_a_trials_plan_change_gives_no_credits_until_its_first_payment(db, billing_reason):
    """On a paid plan's trial days the credits come with the first payment: switching plans
    during the trial doesn't hand out a month. That payment brings it under either name: Lemon
    Squeezy labels an invoice a subscription update produced "updated"."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=4)
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            starter.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=3),
            status="on_trial",
            renews_at=period_end,
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    opening = subscription.current_credits

    await _change_plan(
        db,
        user,
        ls_id,
        growth,
        at=now - timedelta(hours=1),
        period_end=period_end,
        status="on_trial",
    )
    assert (await _subscription_of(db, ls_id)).current_credits == opening

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now - timedelta(minutes=30), billing_reason=billing_reason),
        None,
        db,
    )
    assert (await _subscription_of(db, ls_id)).current_credits == 1000


async def test_the_in_app_plan_change_follows_the_same_rule(db, monkeypatch):
    """The dashboard's change (SubscriptionService.upgrade, which downgrades too) sets the
    credits before Lemon Squeezy's update arrives; that update then changes nothing."""
    user, ls_id, starter, growth, now, period_end = await _starter_spent(db, 300)
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock())
    # A downgrade checks the workspaces and members against the plan's limits: none here.
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})
    usage = UsageTrackingService(db)

    await service.upgrade(user.id, growth.id)
    assert await usage.get_credit_balance(user.id) == 700
    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=1), period_end=period_end)
    assert await usage.get_credit_balance(user.id) == 700

    await service.upgrade(user.id, starter.id)
    assert await usage.get_credit_balance(user.id) == 100
    await service.upgrade(user.id, growth.id)
    assert await usage.get_credit_balance(user.id) == 700


async def test_an_in_app_change_counts_what_is_spent_while_lemon_squeezy_answers(
    db, connection, monkeypatch
):
    """An article spends 50 while the dashboard's change waits on Lemon Squeezy: the change
    counts it, rather than working from the balance it read before."""
    user, ls_id, _, growth, now, period_end = await _starter_spent(db, 300)
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))

    async def spend_meanwhile(**_):
        async with _session(connection) as other:
            assert await UsageTrackingService(other).consume_credits(user.id, 50)
            await other.commit()

    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock(side_effect=spend_meanwhile))
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})

    await service.upgrade(user.id, growth.id)

    assert await UsageTrackingService(db).get_credit_balance(user.id) == 650  # 1,000 less 350


async def test_a_start_from_before_the_marker_is_not_refilled_by_its_created_event_again(db):
    """A subscription stored before the start-month marker existed, running paid: its created
    event delivered again keeps what was spent."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    created = _subscription_event(
        user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=now - timedelta(days=3)
    )
    await handle_subscription_created(created, None, db)
    subscription = await _subscription_of(db, ls_id)
    subscription.subscription_metadata = {
        k: v for k, v in subscription.subscription_metadata.items() if k != "start_month_given"
    }
    await db.flush()
    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 300)

    await handle_subscription_created(created, None, db)

    assert await usage.get_credit_balance(user.id) == 700


async def test_plan_changes_without_a_renewal_date_stay_in_one_period(db):
    """An update without renews_at keeps the stored period, so a change down and back up is
    still counted as one period's: nothing spent comes back."""
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
    assert await usage.consume_credits(user.id, 900)

    for plan, hours_ago in ((starter, 2), (growth, 1)):
        event = _subscription_event(
            user,
            ls_id,
            plan.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(hours=hours_ago),
            name="subscription_updated",
        )
        event["data"]["attributes"]["renews_at"] = None
        await handle_subscription_updated(event, None, db)

    assert await usage.get_credit_balance(user.id) == 100


async def test_an_in_app_change_keeps_the_period_when_renews_at_lags(db, monkeypatch):
    """After a renewal invoice (no renews_at), the stored reset date is the period's end and
    renews_at still the last one. The change keeps the reset date ahead, so the next spend
    doesn't refill the month it has just worked out."""
    user, ls_id, _, growth, now, _ = await _starter_spent(db, 300)
    subscription = await _subscription_of(db, ls_id)
    subscription.renews_at = (now - timedelta(days=1)).replace(tzinfo=None)  # lagging
    subscription.credits_reset_date = now + timedelta(days=29)
    await db.flush()
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock())
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})
    usage = UsageTrackingService(db)

    await service.upgrade(user.id, growth.id)
    assert await usage.consume_credits(user.id, 1)

    assert await usage.get_credit_balance(user.id) == 699  # 1,000 less 300, less 1


async def test_a_paid_start_from_before_the_marker_gets_no_second_month_from_its_invoice(db):
    """Created paid before the marker existed, its first invoice processed after: the month
    it opened with isn't given again over what was spent."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=now),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    subscription.subscription_metadata = {
        k: v for k, v in subscription.subscription_metadata.items() if k != "start_month_given"
    }
    await db.flush()
    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 300)

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now + timedelta(minutes=1), billing_reason="initial"),
        None,
        db,
    )

    assert await usage.get_credit_balance(user.id) == 700


async def test_a_failed_first_payment_from_before_the_marker_gets_its_month_when_paid(db):
    """A start from before the marker whose first payment failed: unpaid, never a trial, no
    payment credited. When the payment comes, it brings the month. The row's status is read
    before the payment activates it, or it would pass for a start that opened paid."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    await handle_subscription_created(
        _subscription_event(user, ls_id, growth.lemonsqueezy_variant_id_monthly, at=now),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    subscription.status = SubscriptionStatus.UNPAID
    subscription.current_credits = 0
    subscription.subscription_metadata = {
        k: v
        for k, v in subscription.subscription_metadata.items()
        if k not in ("start_month_given", "paid_invoice_at")
    }
    await db.flush()

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now + timedelta(minutes=1), billing_reason="initial"),
        None,
        db,
    )

    paid = await _subscription_of(db, ls_id)
    assert paid.status == SubscriptionStatus.ACTIVE
    assert paid.current_credits == 1000
    assert paid.subscription_metadata["start_month_given"] is True


async def test_an_in_app_change_after_the_period_ended_starts_from_a_full_month(db, monkeypatch):
    """The period ended and nothing has refilled it yet (the refill comes with the next spend or
    the renewal's invoice). The change opens the new period: last period's spending isn't taken
    off the new plan, and an earlier change in the ended period doesn't count either."""
    user, ls_id, starter, growth, now, _ = await _starter_spent(db, 300)
    subscription = await _subscription_of(db, ls_id)
    ended = now - timedelta(hours=1)
    subscription.credits_reset_date = ended
    subscription.renews_at = now + timedelta(days=30)
    subscription.subscription_metadata = {
        **(subscription.subscription_metadata or {}),
        "plan_change_credits": {"period": ended.isoformat(), "used": 300, "left": 100},
    }
    await db.flush()
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock())
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})
    usage = UsageTrackingService(db)

    await service.upgrade(user.id, growth.id)

    assert await usage.get_credit_balance(user.id) == 1000
    assert await usage.consume_credits(user.id, 1)
    assert await usage.get_credit_balance(user.id) == 999  # the next spend refills nothing


async def test_lemon_squeezys_change_after_the_period_ended_starts_from_a_full_month(db):
    """The same through Lemon Squeezy's update: the stored period had ended, the update brings
    the next one, and last period's spending isn't taken off the new plan."""
    user, ls_id, _, growth, now, _ = await _starter_spent(db, 300)
    subscription = await _subscription_of(db, ls_id)
    subscription.credits_reset_date = now - timedelta(hours=1)
    await db.flush()

    await _change_plan(
        db, user, ls_id, growth, at=now - timedelta(minutes=5), period_end=now + timedelta(days=30)
    )

    assert await UsageTrackingService(db).get_credit_balance(user.id) == 1000


async def _trial_from_before_the_marker(db, plan, now):
    """A subscriber on a paid plan's trial days whose row predates the start-month marker."""
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            plan.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=3),
            status="on_trial",
            renews_at=now + timedelta(days=4),
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    subscription.trial_end_date = now + timedelta(days=4)
    subscription.subscription_metadata = {
        k: v for k, v in subscription.subscription_metadata.items() if k != "start_month_given"
    }
    await db.flush()
    return user, ls_id


@pytest.mark.parametrize("billing_reason", ["initial", "updated"])
async def test_a_trial_from_before_the_marker_upgraded_in_the_app_gets_its_month_when_paid(
    db, monkeypatch, billing_reason
):
    """The in-app change makes the trial active and clears its end date. The row says first
    that it hasn't had its month, so the first payment still brings it: the invoice the change
    asks for at once, which Lemon Squeezy labels "updated", or one labelled "initial"."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    now = datetime.now(timezone.utc)
    user, ls_id = await _trial_from_before_the_marker(db, starter, now)
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock())
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})

    await service.upgrade(user.id, growth.id)
    upgraded = await _subscription_of(db, ls_id)
    assert upgraded.status == SubscriptionStatus.ACTIVE
    assert upgraded.trial_end_date is None
    assert upgraded.subscription_metadata["start_month_given"] is False

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now + timedelta(minutes=1), billing_reason=billing_reason),
        None,
        db,
    )

    paid = await _subscription_of(db, ls_id)
    assert paid.current_credits == 1000
    assert paid.subscription_metadata["start_month_given"] is True

    # It brought the month once. A later plan change's prorated payment, under the same
    # name, brings nothing: the customer keeps what the spending left.
    assert await UsageTrackingService(db).consume_credits(user.id, 300)
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now + timedelta(minutes=9), billing_reason="updated"),
        None,
        db,
    )
    assert await UsageTrackingService(db).get_credit_balance(user.id) == 700


async def test_a_trial_from_before_the_marker_that_converts_gets_its_month_when_paid(db):
    """Lemon Squeezy's update ends the trial first (active, no trial date), then the invoice
    comes: the row kept its answer, so the first payment brings the month."""
    starter = await _plan(db, "starter", price=39, credits=400)
    now = datetime.now(timezone.utc)
    user, ls_id = await _trial_from_before_the_marker(db, starter, now)

    await _change_plan(
        db, user, ls_id, starter, at=now - timedelta(minutes=5), period_end=now + timedelta(days=30)
    )
    converted = await _subscription_of(db, ls_id)
    assert converted.status == SubscriptionStatus.ACTIVE
    assert converted.trial_end_date is None

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now + timedelta(minutes=1), billing_reason="initial"),
        None,
        db,
    )

    assert (await _subscription_of(db, ls_id)).current_credits == 400


@pytest.mark.parametrize("first", ["initial", "updated"])
async def test_a_trial_that_converts_by_itself_gets_its_month_exactly_once(db, first):
    """No plan change: the trial ends and its first payment brings the month, whichever name
    the invoice carries. No later payment of either name brings it again: a retry of the
    first, or a prorated invoice. The customer keeps what the spending left."""
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=7),
            status="on_trial",
            renews_at=now + timedelta(days=30),
        ),
        None,
        db,
    )
    assert (await _subscription_of(db, ls_id)).subscription_metadata["start_month_given"] is False

    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now, billing_reason=first), None, db
    )

    converted = await _subscription_of(db, ls_id)
    assert converted.current_credits == 1000
    assert converted.subscription_metadata["start_month_given"] is True

    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 300)
    for minutes, again in enumerate(("initial", "updated"), 5):
        await handle_subscription_payment_success(
            _invoice_event(user, ls_id, at=now + timedelta(minutes=minutes), billing_reason=again),
            None,
            db,
        )
        assert await usage.get_credit_balance(user.id) == 700


async def test_a_converted_trial_changing_plan_before_it_pays_keeps_its_balance(db):
    """Lemon Squeezy's update made the trial active; a plan change arrives before the first
    payment. The balance stays as it is, and the payment brings the new plan's month. After
    that a plan change works from what was used."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    now = datetime.now(timezone.utc)
    user, ls_id = await _trial_from_before_the_marker(db, starter, now)
    period_end = now + timedelta(days=30)
    await _change_plan(
        db, user, ls_id, starter, at=now - timedelta(minutes=9), period_end=period_end
    )
    before = (await _subscription_of(db, ls_id)).current_credits

    await _change_plan(
        db, user, ls_id, growth, at=now - timedelta(minutes=8), period_end=period_end
    )
    assert (await _subscription_of(db, ls_id)).current_credits == before

    # The first paid invoice, whatever Lemon Squeezy calls it, brings the month and settles it.
    await handle_subscription_payment_success(
        _invoice_event(user, ls_id, at=now - timedelta(minutes=7), billing_reason="renewal"),
        None,
        db,
    )
    paid = await _subscription_of(db, ls_id)
    assert paid.current_credits == 1000
    assert paid.subscription_metadata["start_month_given"] is True

    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 100)
    await _change_plan(
        db, user, ls_id, starter, at=now - timedelta(minutes=5), period_end=period_end
    )
    assert await usage.get_credit_balance(user.id) == 300  # 400 less the 100 used


async def test_an_in_app_change_then_lemon_squeezys_change_back_stay_in_one_period(db, monkeypatch):
    """The dashboard's change keeps the stored period end; Lemon Squeezy's next change brings
    its renews_at. Both are one period: 900 spent, down to Starter and back up leaves 100."""
    starter = await _plan(db, "starter", price=39, credits=400)
    growth = await _plan(db, "growth", price=89, credits=1000)
    user = await _customer(db)
    ls_id = uuid4().int % 10**9
    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=27)
    await handle_subscription_created(
        _subscription_event(
            user,
            ls_id,
            growth.lemonsqueezy_variant_id_monthly,
            at=now - timedelta(days=3),
            renews_at=period_end,
        ),
        None,
        db,
    )
    subscription = await _subscription_of(db, ls_id)
    subscription.credits_reset_date = period_end - timedelta(hours=5)  # a renewal invoice's
    await db.flush()
    usage = UsageTrackingService(db)
    assert await usage.consume_credits(user.id, 900)
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    service = SubscriptionService(db)
    service.payment_provider = MagicMock(update_subscription=AsyncMock())
    service.calculate_usage = AsyncMock(return_value={"workspaces": 0, "members": 0})

    await service.upgrade(user.id, starter.id)
    assert await usage.get_credit_balance(user.id) == 0
    await _change_plan(db, user, ls_id, growth, at=now - timedelta(hours=1), period_end=period_end)

    assert await usage.get_credit_balance(user.id) == 100


@pytest.mark.xfail(
    datetime.now().astimezone().utcoffset() != timedelta(0),
    strict=True,
    reason="F20 rext-control#655: off UTC, ends_at is stored moved by the host's offset",
)
async def test_a_cancelled_plan_keeps_access_until_its_end_then_expires(db, clock):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_cancelled,
        handle_subscription_expired,
    )

    now = datetime.now(timezone.utc).replace(microsecond=0)
    ends = now + timedelta(days=5)
    clock(now)
    user, ls_id, growth = await _active_growth(db)
    usage = UsageTrackingService(db)
    cancelled = _subscription_event(
        user,
        ls_id,
        growth.lemonsqueezy_variant_id_monthly,
        at=now - timedelta(minutes=10),
        status="cancelled",
        name="subscription_cancelled",
    )
    cancelled["data"]["attributes"]["cancelled"] = True
    cancelled["data"]["attributes"]["ends_at"] = _iso(ends)

    await handle_subscription_cancelled(cancelled, None, db)
    assert (await _subscription_of(db, ls_id)).status.value == "cancelled"
    assert await usage.consume_credits(user.id, 15)  # paid through: still writing
    clock(ends - timedelta(seconds=1))
    assert await usage.consume_credits(user.id, 15)  # the last second paid for

    # The paid-through date ends access by itself, before Lemon Squeezy's expiry event.
    clock(ends)
    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False

    expired = _subscription_event(
        user,
        ls_id,
        growth.lemonsqueezy_variant_id_monthly,
        at=ends,
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
def refund_fakes(monkeypatch):
    """No email and no Lemon Squeezy for a refund: the fake provider it returns takes the
    cancel that every full refund makes there (F8c)."""
    from unittest.mock import AsyncMock, MagicMock

    import src.providers.payment.provider_factory as provider_factory
    import src.services.webhook_handlers.order_handlers as order_handlers
    import src.services.webhook_handlers.renewal_refund_handlers as renewal_refund_handlers

    provider = MagicMock()
    provider.cancel_subscription = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(provider_factory, "get_payment_provider", lambda: provider)
    for handlers in (order_handlers, renewal_refund_handlers):
        monkeypatch.setattr(handlers, "get_payment_provider", lambda: provider)
        monkeypatch.setattr(handlers, "send_billing_email_in_background", AsyncMock())
    return provider


async def test_a_full_refund_of_the_first_payment_ends_access(db, refund_fakes):
    from src.services.webhook_handlers.order_handlers import handle_order_refunded

    user, order_id = await _paid_growth(db)
    variant = (await db.execute(select(SubscriptionPlan))).scalars().first()

    await handle_order_refunded(
        _refund_event(user, order_id, variant.lemonsqueezy_variant_id_monthly), None, db
    )

    usage = UsageTrackingService(db)
    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False


async def test_a_full_refund_of_a_renewal_ends_that_months_credits(db, refund_fakes):
    """The refund rule covers any payment: refunding a renewal takes back that month.

    Lemon Squeezy bills a renewal as a subscription invoice, not an order, and its refund
    arrives as subscription_payment_refunded for that invoice (F8b, rext-control#537).
    """
    from src.services.webhook_handlers.renewal_refund_handlers import (
        handle_subscription_payment_refunded,
    )

    user, ls_id, _ = await _active_growth(db)
    now = datetime.now(timezone.utc)
    renewal = _invoice_event(user, ls_id, at=now - timedelta(days=1), billing_reason="renewal")
    await handle_subscription_payment_success(renewal, None, db)
    usage = UsageTrackingService(db)
    assert await usage.get_credit_balance(user.id) == 1000

    refund = _invoice_event(
        user,
        ls_id,
        at=now - timedelta(days=1),
        billing_reason="renewal",
        status="refunded",
        name="subscription_payment_refunded",
    )
    refund["data"]["id"] = renewal["data"]["id"]
    refund["data"]["attributes"].update(
        {"refunded": True, "refunded_amount": 8900, "refunded_at": _iso(now)}
    )
    await handle_subscription_payment_refunded(refund, None, db)

    assert await usage.get_credit_balance(user.id) == 0
    assert await usage.consume_credits(user.id, 15) is False
    # Lemon Squeezy's subscription ends too, or it charges the refunded customer next month.
    refund_fakes.cancel_subscription.assert_awaited()


async def test_a_refunded_plan_is_not_revived_by_lemon_squeezys_next_update(db, refund_fakes):
    """A full refund cancels the subscription at Lemon Squeezy, and an "active" update without a
    new payment doesn't bring access back."""
    from src.services.webhook_handlers.order_handlers import handle_order_refunded

    provider = refund_fakes
    user, order_id = await _paid_growth(db)
    plan = (await db.execute(select(SubscriptionPlan))).scalars().first()
    variant = plan.lemonsqueezy_variant_id_monthly
    subscription = (
        await db.execute(select(UserSubscription).where(UserSubscription.user_id == user.id))
    ).scalar_one()
    await handle_order_refunded(_refund_event(user, order_id, variant), None, db)

    # Lemon Squeezy's subscription ends too, or it charges the refunded customer next month.
    provider.cancel_subscription.assert_awaited()
    assert subscription.lemonsqueezy_subscription_id in str(provider.cancel_subscription.await_args)

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
