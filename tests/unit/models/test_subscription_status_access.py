"""Lemon Squeezy's subscription status decides access (F11, revnix/rext-control#336).

A failed renewal is PAST_DUE while Lemon Squeezy retries it, and keeps the plan;
UNPAID (the retries ran out) and EXPIRED lose it; CANCELLED keeps it until its
end_date. There is no grace deadline of our own any more.

The access rule is a SQL filter, so it is checked on the test PostgreSQL: the
tables it needs are created inside a transaction that is rolled back, so nothing
is left behind whatever the test database already holds.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.exceptions import DuplicateResourceException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
    lemonsqueezy_status,
    subscription_grants_access,
)
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.services.subscription_service import SubscriptionService
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
LATER, EARLIER = NOW + timedelta(days=3), NOW - timedelta(days=1)


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
                    Promotion.__table__,  # the balance counts credit grants
                    CreditGrant.__table__,
                    WorkspaceModel.__table__,  # audit_logs refers to it
                    AuditLog.__table__,  # cancel() and the handlers record themselves
                ],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _subscription(db, status, *, end=None, credits=600, reset=None, ls_id=None):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}",
        display_name="Growth",
        price_monthly=89,
        price_yearly=890,
        credits_per_month=1000,
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        end_date=end,
        current_credits=credits,
        credits_reset_date=reset,
        lemonsqueezy_subscription_id=ls_id,
    )
    db.add(subscription)
    await db.flush()
    return user, plan, subscription


async def _grants(db, subscription) -> bool:
    found = await db.execute(
        select(UserSubscription.id).where(
            UserSubscription.id == subscription.id, subscription_grants_access(NOW)
        )
    )
    return found.scalar_one_or_none() is not None


async def _row(session, subscription):
    return (
        await session.execute(
            select(
                UserSubscription.status,
                UserSubscription.end_date,
                UserSubscription.cancel_at_period_end,
                UserSubscription.payment_failed_at,
                UserSubscription.current_credits,
            ).where(UserSubscription.id == subscription.id)
        )
    ).one()


def _event(event_type):
    return SimpleNamespace(id=uuid4(), event_type=event_type)


def _subscription_payload(ls_id, **attributes):
    return {"data": {"type": "subscriptions", "id": ls_id, "attributes": attributes}}


def _invoice_payload(ls_id):
    return {
        "data": {
            "type": "subscription-invoices",
            "id": f"inv-{uuid4().hex[:6]}",
            "attributes": {"subscription_id": ls_id, "total": 8900},
        }
    }


# --- the status map and the access rule -----------------------------------------


@pytest.mark.parametrize(
    ("provider", "stored"),
    [
        ("on_trial", SubscriptionStatus.TRIAL),
        ("active", SubscriptionStatus.ACTIVE),
        ("paused", SubscriptionStatus.PAUSED),
        ("past_due", SubscriptionStatus.PAST_DUE),
        ("unpaid", SubscriptionStatus.UNPAID),
        ("cancelled", SubscriptionStatus.CANCELLED),
        ("expired", SubscriptionStatus.EXPIRED),
        ("PAST_DUE", SubscriptionStatus.PAST_DUE),
        ("", SubscriptionStatus.ACTIVE),
        (None, SubscriptionStatus.ACTIVE),
    ],
)
def test_lemon_squeezy_statuses_are_stored_as_they_are(provider, stored):
    assert lemonsqueezy_status(provider) == stored


@pytest.mark.parametrize(
    ("status", "end", "expected"),
    [
        (SubscriptionStatus.ACTIVE, None, True),
        (SubscriptionStatus.TRIAL, None, True),
        # Lemon Squeezy is retrying the failed renewal: the plan stays.
        (SubscriptionStatus.PAST_DUE, None, True),
        # Its retries ran out: no plan until the card is updated.
        (SubscriptionStatus.UNPAID, None, False),
        (SubscriptionStatus.EXPIRED, LATER, False),
        (SubscriptionStatus.PAUSED, None, False),
        # The old grace's status is no longer an access state (the migration moved its rows).
        (SubscriptionStatus.SUSPENDED, None, False),
        (SubscriptionStatus.CANCELLED, LATER, True),
        (SubscriptionStatus.CANCELLED, EARLIER, False),
    ],
)
@pytest.mark.asyncio
async def test_access_follows_the_status(session, status, end, expected):
    _, _, subscription = await _subscription(session, status, end=end)

    assert await _grants(session, subscription) is expected


@pytest.mark.asyncio
async def test_credits_endpoint_keeps_the_plan_while_past_due(session):
    from src.api.server import app

    user, _, _ = await _subscription(session, SubscriptionStatus.PAST_DUE)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/subscriptions/credits")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["current_credits"] == 600
    assert data["plan_name"] == "Growth"


# --- credits and new subscriptions while a renewal is unpaid ----------------------


@pytest.mark.parametrize(
    ("status", "balance_after"),
    [
        # The renewal failed at the reset date: no new month until the payment succeeds.
        (SubscriptionStatus.PAST_DUE, 600 - 15),
        # A paid subscription past its reset date is refilled first, as before.
        (SubscriptionStatus.ACTIVE, 1000 - 15),
    ],
)
@pytest.mark.asyncio
async def test_no_new_month_of_credits_while_a_renewal_is_unpaid(session, status, balance_after):
    from src.services.usage_tracking_service import UsageTrackingService

    user, _, subscription = await _subscription(session, status, reset=NOW - timedelta(hours=2))

    assert await UsageTrackingService(session).consume_credits(user.id, 15) is True
    assert (await _row(session, subscription)).current_credits == balance_after


@pytest.mark.parametrize("status", [SubscriptionStatus.PAST_DUE, SubscriptionStatus.UNPAID])
@pytest.mark.asyncio
async def test_a_second_subscription_is_refused_while_a_renewal_is_unpaid(session, status):
    # UNPAID grants no access, so the guard has to find it without the access filter.
    user, _, _ = await _subscription(session, status, ls_id=f"ls-sub-guard-{status.value}")
    service = SubscriptionService(session)

    with pytest.raises(DuplicateResourceException) as subscribing:
        await service.subscribe(
            user_id=user.id, plan_id=uuid4(), billing_period=BillingPeriod.MONTHLY
        )
    with pytest.raises(DuplicateResourceException) as checking_out:
        await service.create_checkout(
            user_id=user.id,
            plan_id=uuid4(),
            billing_period=BillingPeriod.MONTHLY,
            success_url="https://app.example.com/ok",
            cancel_url="https://app.example.com/cancel",
        )
    # downgrade() goes through upgrade(), so both routes are covered.
    with pytest.raises(DuplicateResourceException) as changing:
        await service.upgrade(user.id, uuid4(), BillingPeriod.MONTHLY)

    for raised in (subscribing, checking_out):
        assert "Update your payment method" in raised.value.message
    assert "your plan can change once the payment goes through" in changing.value.message


def test_an_active_subscription_blocks_nothing():
    from src.services.subscription_service import _refuse_during_payment_retry

    _refuse_during_payment_retry(SimpleNamespace(status=SubscriptionStatus.ACTIVE), uuid4())


def test_the_access_filter_names_the_statuses_the_migrated_type_holds():
    """Migration e52e15b5c2ea renamed past_due and paused to the enum's names, so the
    filter can name PAST_DUE; every name it uses is a label of the migrated type."""
    from sqlalchemy.dialects import postgresql

    sql = str(
        select(UserSubscription.id)
        .where(subscription_grants_access(NOW))
        .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )

    labels = {
        "ACTIVE",
        "CANCELLED",
        "EXPIRED",
        "TRIAL",
        "SUSPENDED",
        "PAST_DUE",
        "UNPAID",
        "PAUSED",
    }
    assert {member.name for member in SubscriptionStatus} == labels
    for name in ("ACTIVE", "TRIAL", "PAST_DUE", "CANCELLED"):
        assert f"'{name}'" in sql


# --- the webhooks ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_payment_makes_the_subscription_past_due(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_failed,
    )

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.ACTIVE, ls_id="ls-sub-failed"
    )

    await handle_subscription_payment_failed(
        _invoice_payload("ls-sub-failed"), _event("subscription_payment_failed"), session
    )
    row = await _row(session, subscription)

    assert row.status == SubscriptionStatus.PAST_DUE
    assert row.payment_failed_at is not None
    assert row.end_date is None  # no deadline of our own
    assert await _grants(session, subscription) is True


@pytest.mark.parametrize(
    ("status", "end"),
    [
        (SubscriptionStatus.CANCELLED, LATER),
        (SubscriptionStatus.EXPIRED, EARLIER),
        (SubscriptionStatus.UNPAID, None),
    ],
)
@pytest.mark.asyncio
async def test_a_failed_payment_never_moves_an_ending(session, status, end):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_failed,
    )

    ls_id = f"ls-sub-{status.value}"
    _, _, subscription = await _subscription(session, status, end=end, ls_id=ls_id)

    await handle_subscription_payment_failed(
        _invoice_payload(ls_id), _event("subscription_payment_failed"), session
    )
    row = await _row(session, subscription)

    assert row.status == status
    assert row.end_date == end


@pytest.mark.parametrize(
    ("provider_status", "stored", "access"),
    [
        ("past_due", SubscriptionStatus.PAST_DUE, True),
        ("unpaid", SubscriptionStatus.UNPAID, False),
        ("paused", SubscriptionStatus.PAUSED, False),
        ("active", SubscriptionStatus.ACTIVE, True),
    ],
)
@pytest.mark.asyncio
async def test_an_update_stores_lemon_squeezys_status(session, provider_status, stored, access):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

    ls_id = f"ls-sub-upd-{provider_status}"
    _, _, subscription = await _subscription(session, SubscriptionStatus.PAST_DUE, ls_id=ls_id)

    await handle_subscription_updated(
        _subscription_payload(ls_id, status=provider_status),
        _event("subscription_updated"),
        session,
    )

    assert (await _row(session, subscription)).status == stored
    assert await _grants(session, subscription) is access


@pytest.mark.asyncio
async def test_the_cancellation_webhook_ends_at_lemon_squeezys_ends_at(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_cancelled,
    )

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.PAST_DUE, ls_id="ls-sub-cancel"
    )
    ends_at = NOW + timedelta(days=20)

    await handle_subscription_cancelled(
        _subscription_payload("ls-sub-cancel", ends_at=ends_at.isoformat()),
        _event("subscription_cancelled"),
        session,
    )
    row = await _row(session, subscription)

    assert row.status == SubscriptionStatus.CANCELLED
    # Lemon Squeezy's ends_at, not a deadline of ours. The handlers store naive UTC,
    # which the driver reads as the machine's local time, so off-UTC machines see it
    # shifted by their offset (at most 14 hours).
    assert abs(row.end_date - ends_at) <= timedelta(hours=14)
    assert await _grants(session, subscription) is True


@pytest.mark.parametrize(
    ("provider_status", "stored"),
    [("past_due", SubscriptionStatus.PAST_DUE), ("active", SubscriptionStatus.ACTIVE)],
)
@pytest.mark.asyncio
async def test_a_resume_takes_lemon_squeezys_status_and_no_longer_ends(
    session, provider_status, stored
):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_resumed

    ls_id = f"ls-sub-resume-{provider_status}"
    _, _, subscription = await _subscription(
        session, SubscriptionStatus.CANCELLED, end=LATER, ls_id=ls_id
    )
    subscription.cancel_at_period_end = True
    await session.flush()

    await handle_subscription_resumed(
        _subscription_payload(ls_id, status=provider_status),
        _event("subscription_resumed"),
        session,
    )
    row = await _row(session, subscription)

    assert row.status == stored
    assert row.end_date is None
    assert row.cancel_at_period_end is False


@pytest.mark.parametrize("status", [SubscriptionStatus.PAST_DUE, SubscriptionStatus.UNPAID])
@pytest.mark.asyncio
async def test_a_successful_payment_makes_it_active_with_the_new_month(session, status):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_success,
    )

    ls_id = f"ls-sub-paid-{status.value}"
    _, _, subscription = await _subscription(session, status, ls_id=ls_id)

    await handle_subscription_payment_success(
        _invoice_payload(ls_id), _event("subscription_payment_success"), session
    )
    row = await _row(session, subscription)

    assert row.status == SubscriptionStatus.ACTIVE
    assert row.current_credits == 1000  # the new month comes with the payment


@pytest.mark.asyncio
async def test_cancelling_while_past_due_ends_at_the_paid_period(session):
    user, _, subscription = await _subscription(session, SubscriptionStatus.PAST_DUE)
    subscription.renews_at = EARLIER  # the renewal that failed
    await session.flush()

    await SubscriptionService(session).cancel(user.id)
    row = await _row(session, subscription)

    # Nothing was paid past the failed renewal, so no new period is owed.
    assert row.status == SubscriptionStatus.CANCELLED
    assert await _grants(session, subscription) is False


# --- the emails -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_failed_attempt_s_email_names_the_first_failure(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_failed,
    )

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.PAST_DUE, ls_id="ls-sub-email"
    )
    first_failure = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    subscription.payment_failed_at = first_failure
    await session.flush()

    task = await handle_subscription_payment_failed(
        _invoice_payload("ls-sub-email"), _event("subscription_payment_failed"), session
    )

    assert task["email_type"] == "payment_failed"
    assert task["email_data"]["failed_on"] == "October 01, 2026"
    assert "retry_date" not in task["email_data"]


@pytest.mark.asyncio
async def test_becoming_unpaid_sends_one_email(session):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.PAST_DUE, ls_id="ls-sub-unpaid"
    )
    unpaid = _subscription_payload("ls-sub-unpaid", status="unpaid")

    first = await handle_subscription_updated(unpaid, _event("subscription_updated"), session)
    again = await handle_subscription_updated(unpaid, _event("subscription_updated"), session)

    assert first["email_type"] == "subscription_unpaid"
    assert first["email_data"] == {
        "user_id": str(subscription.user_id),
        "plan_name": "Growth",
        "subscription_id": str(subscription.id),
    }
    assert again is None  # already unpaid: no second email


# --- event order and credits ------------------------------------------------------

T1, T2, T3 = (datetime(2026, 10, 6, h, 0, tzinfo=timezone.utc) for h in (8, 9, 10))


@pytest.mark.asyncio
async def test_an_older_update_is_ignored_and_a_newer_one_applied(session):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.ACTIVE, ls_id="ls-sub-order"
    )
    subscription.provider_updated_at = T2
    await session.flush()

    late = _subscription_payload("ls-sub-order", status="past_due", updated_at=T1.isoformat())
    await handle_subscription_updated(late, _event("subscription_updated"), session)
    assert (await _row(session, subscription)).status == SubscriptionStatus.ACTIVE

    newer = _subscription_payload("ls-sub-order", status="unpaid", updated_at=T3.isoformat())
    await handle_subscription_updated(newer, _event("subscription_updated"), session)
    await session.refresh(subscription)
    assert subscription.status == SubscriptionStatus.UNPAID
    assert subscription.provider_updated_at == T3


@pytest.mark.asyncio
async def test_an_older_cancellation_is_ignored(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_cancelled,
    )

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.ACTIVE, ls_id="ls-sub-old-cancel"
    )
    subscription.provider_updated_at = T2
    await session.flush()

    await handle_subscription_cancelled(
        _subscription_payload(
            "ls-sub-old-cancel", ends_at=LATER.isoformat(), updated_at=T1.isoformat()
        ),
        _event("subscription_cancelled"),
        session,
    )

    assert (await _row(session, subscription)).status == SubscriptionStatus.ACTIVE


@pytest.mark.parametrize(
    ("provider_status", "credits"), [("active", 1000), ("on_trial", 0), ("past_due", 0)]
)
@pytest.mark.asyncio
async def test_a_new_subscription_gets_credits_only_once_paid(session, provider_status, credits):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

    user, plan, _ = await _subscription(session, SubscriptionStatus.EXPIRED)
    plan.lemonsqueezy_variant_id_monthly = f"var-{provider_status}"
    await session.flush()
    ls_id = f"ls-sub-new-{provider_status}"
    payload = _subscription_payload(
        ls_id,
        status=provider_status,
        variant_id=f"var-{provider_status}",
        user_email=user.email,
        updated_at=T1.isoformat(),
    )
    payload["custom_data"] = {"user_id": str(user.id)}

    await handle_subscription_updated(payload, _event("subscription_updated"), session)
    created = (
        await session.execute(
            select(UserSubscription).where(UserSubscription.lemonsqueezy_subscription_id == ls_id)
        )
    ).scalar_one()

    assert created.current_credits == credits
    assert created.provider_updated_at == T1


@pytest.mark.asyncio
async def test_a_payment_for_an_unknown_subscription_fails_to_be_retried(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_success,
    )

    with pytest.raises(ValueError, match="not found in payment_success"):
        await handle_subscription_payment_success(
            _invoice_payload("ls-sub-not-yet"), _event("subscription_payment_success"), session
        )


@pytest.mark.asyncio
async def test_a_new_failure_episode_starts_its_own_date(session):
    from src.services.webhook_handlers.subscription_handlers import (
        handle_subscription_payment_failed,
    )

    _, _, subscription = await _subscription(
        session, SubscriptionStatus.ACTIVE, ls_id="ls-sub-epoch"
    )
    old_episode = datetime(2026, 7, 1, tzinfo=timezone.utc)  # recovered months ago
    subscription.payment_failed_at = old_episode
    await session.flush()

    first = await handle_subscription_payment_failed(
        _invoice_payload("ls-sub-epoch"), _event("subscription_payment_failed"), session
    )
    started = (await _row(session, subscription)).payment_failed_at
    retried = await handle_subscription_payment_failed(
        _invoice_payload("ls-sub-epoch"), _event("subscription_payment_failed"), session
    )

    assert started > old_episode
    assert (await _row(session, subscription)).payment_failed_at == started  # retries keep it
    assert first["email_data"]["failed_on"] == retried["email_data"]["failed_on"]
    assert first["email_data"]["failed_on"] != "July 01, 2026"


@pytest.mark.asyncio
async def test_a_subscription_first_seen_unpaid_still_sends_the_email(session):
    from src.services.webhook_handlers.subscription_handlers import handle_subscription_updated

    user, plan, _ = await _subscription(session, SubscriptionStatus.EXPIRED)
    plan.lemonsqueezy_variant_id_monthly = "var-unpaid-first"
    await session.flush()
    payload = _subscription_payload(
        "ls-sub-first-unpaid",
        status="unpaid",
        variant_id="var-unpaid-first",
        user_email=user.email,
        updated_at=T1.isoformat(),
    )
    payload["custom_data"] = {"user_id": str(user.id)}

    task = await handle_subscription_updated(payload, _event("subscription_updated"), session)

    assert task["email_type"] == "subscription_unpaid"
