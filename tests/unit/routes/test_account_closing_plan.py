"""Closing an account stops renewals; the plan runs to the end of the paid period.

Founder decision on F12 (revnix/rext-control#337, 2026-10-06): Lemon Squeezy only
cancels at the period end, so the app no longer claims an immediate end. It says
until when the plan stays active. Checked on the test PostgreSQL inside a
rolled-back transaction, with Lemon Squeezy and the email replaced by mocks.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.subscription_service as service_module
from src.api.database.async_database import get_async_db
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from src.api.security.token_utils import hash_password
from tests.conftest import TEST_DATABASE_URL
from tests.db_tables import create_tables_unless_migrated

PAID_UNTIL = (datetime.now(timezone.utc) + timedelta(days=17)).replace(microsecond=0)
PASSWORD = "a-test-password-1"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: create_tables_unless_migrated(
                sync,
                # Closing an account also reads roles and ends sessions.
                [UserSubscription, AuditLog, UserRole, UserSession, TokenBlacklist],
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def provider(monkeypatch):
    fake = AsyncMock()
    monkeypatch.setattr(service_module, "get_payment_provider_singleton", lambda: fake)
    monkeypatch.setattr(service_module, "invalidate_cache", AsyncMock())
    return fake


async def _customer(db, status, *, ls_id="ls-close", renews_at=PAID_UNTIL, end_date=None):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=1000
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com", password_hash=hash_password(PASSWORD))
    db.add_all([plan, user])
    await db.flush()
    subscription = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        lemonsqueezy_subscription_id=f"{ls_id}-{uuid4().hex[:6]}" if ls_id else None,
        renews_at=renews_at,
        end_date=end_date,
    )
    db.add(subscription)
    await db.flush()
    return user, subscription


async def _close(session, user, cancel_subscriptions=True):
    from src.api.routes.users import user_status
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    email = AsyncMock()
    try:
        with patch.object(user_status, "send_deactivation_email_task", email):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/user/deactivate",
                    json={
                        "password": PASSWORD,
                        "confirm": True,
                        "cancel_subscriptions": cancel_subscriptions,
                    },
                )
    finally:
        app.dependency_overrides.clear()
    return response, email


@pytest.mark.parametrize("status", [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE])
@pytest.mark.asyncio
async def test_closing_stops_renewals_and_keeps_the_paid_period(session, provider, status):
    user, subscription = await _customer(session, status)

    response, email = await _close(session, user)

    assert response.status_code == 200, response.text
    provider.cancel_subscription.assert_awaited_once_with(
        subscription_id=subscription.lemonsqueezy_subscription_id, at_period_end=True
    )
    row = (
        await session.execute(
            select(UserSubscription).where(UserSubscription.id == subscription.id)
        )
    ).scalar_one()
    assert row.status == SubscriptionStatus.CANCELLED
    assert row.cancel_at_period_end is True
    assert row.end_date == PAID_UNTIL
    data = response.json()["data"]
    assert datetime.fromisoformat(data["plan_ends_at"]) == PAID_UNTIL
    assert f"stays active until {PAID_UNTIL:%B %d, %Y}" in data["message"]
    assert email.call_args.kwargs["plan_ends_on"] == f"{PAID_UNTIL:%B %d, %Y}"
    # The plan outlasts the account's 14 days: it's usable only by logging back in first.
    deleted_on = datetime.fromisoformat(data["scheduled_deletion_at"])
    assert f"If you log back in before {deleted_on:%B %d, %Y}" in data["message"]
    assert email.call_args.kwargs["log_back_in_by"] == f"{deleted_on:%B %d, %Y}"


@pytest.mark.asyncio
async def test_a_past_due_plan_counts_as_active_when_closing(session, provider):
    user, _ = await _customer(session, SubscriptionStatus.PAST_DUE)

    response, _ = await _close(session, user, cancel_subscriptions=False)

    # Lemon Squeezy is still retrying its payment: it isn't left running unasked.
    assert response.status_code in (400, 422), response.text
    assert "active subscriptions" in response.text
    provider.cancel_subscription.assert_not_called()


@pytest.mark.asyncio
async def test_an_immediate_cancel_of_a_billed_plan_ends_at_the_paid_period(session, provider):
    user, subscription = await _customer(session, SubscriptionStatus.ACTIVE)

    await service_module.SubscriptionService(session).cancel(user.id, cancel_immediately=True)

    provider.cancel_subscription.assert_awaited_once_with(
        subscription_id=subscription.lemonsqueezy_subscription_id, at_period_end=True
    )
    assert subscription.end_date == PAID_UNTIL
    assert subscription.cancel_at_period_end is True


@pytest.mark.asyncio
async def test_a_local_trial_can_still_end_at_once(session, provider):
    user, subscription = await _customer(session, SubscriptionStatus.TRIAL, ls_id=None)

    await service_module.SubscriptionService(session).cancel(user.id, cancel_immediately=True)

    provider.cancel_subscription.assert_not_called()
    assert subscription.end_date <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_closing_is_refused_when_the_renewals_cannot_be_stopped(session, provider):
    user, _ = await _customer(session, SubscriptionStatus.ACTIVE)
    provider.cancel_subscription.side_effect = RuntimeError("Lemon Squeezy is down")

    response, email = await _close(session, user)

    assert response.status_code in (400, 422), response.text
    assert "still open" in response.text
    # Refused before the account is deactivated: the request rolls back, no email goes.
    email.assert_not_called()
    provider.cancel_subscription.assert_awaited_once()


@pytest.mark.asyncio
async def test_closing_takes_the_period_end_from_lemon_squeezy(session, provider):
    stale_local_date = PAID_UNTIL - timedelta(days=9)
    user, subscription = await _customer(
        session, SubscriptionStatus.ACTIVE, renews_at=stale_local_date
    )
    provider.cancel_subscription.return_value = SimpleNamespace(current_period_end=PAID_UNTIL)

    response, _ = await _close(session, user)

    assert response.status_code == 200, response.text
    assert subscription.end_date == PAID_UNTIL
    assert datetime.fromisoformat(response.json()["data"]["plan_ends_at"]) == PAID_UNTIL


@pytest.mark.asyncio
async def test_a_plan_cancelled_earlier_still_says_until_when(session, provider):
    user, _ = await _customer(session, SubscriptionStatus.CANCELLED, end_date=PAID_UNTIL)

    response, email = await _close(session, user, cancel_subscriptions=False)

    assert response.status_code == 200, response.text
    provider.cancel_subscription.assert_not_called()
    assert datetime.fromisoformat(response.json()["data"]["plan_ends_at"]) == PAID_UNTIL
    assert email.call_args.kwargs["plan_ends_on"] == f"{PAID_UNTIL:%B %d, %Y}"


@pytest.mark.parametrize(
    "status, ls_id, renews_at",
    [
        # Lemon Squeezy is retrying the renewal that failed: that period isn't paid.
        (SubscriptionStatus.PAST_DUE, "ls-close", PAID_UNTIL - timedelta(days=30)),
        # A trial Lemon Squeezy doesn't bill ends with the account.
        (SubscriptionStatus.TRIAL, None, None),
    ],
)
@pytest.mark.asyncio
async def test_no_date_is_promised_for_a_plan_that_ends_now(
    session, provider, status, ls_id, renews_at
):
    user, subscription = await _customer(session, status, ls_id=ls_id, renews_at=renews_at)

    response, email = await _close(session, user)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["plan_ends_at"] is None
    assert "Your plan has ended." in data["message"]
    assert "stays active" not in data["message"]
    assert email.call_args.kwargs["plan_ends_on"] is None
    assert subscription.end_date <= datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_the_cancel_endpoint_says_what_happened_not_what_was_asked(
    session, provider, monkeypatch
):
    from src.api.routes.subscriptions import subscription_routes
    from src.api.server import app

    user, _ = await _customer(session, SubscriptionStatus.ACTIVE)
    monkeypatch.setattr(subscription_routes, "schedule_if_allowed", AsyncMock())
    monkeypatch.setattr(service_module, "schedule_if_allowed", AsyncMock())

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/subscriptions/cancel", json={"cancel_immediately": True}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    assert response.json()["message"] == f"Subscription will end on {PAID_UNTIL:%Y-%m-%d}"


@pytest.mark.asyncio
async def test_a_plan_ending_before_the_deletion_names_only_its_end(session, provider):
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).replace(microsecond=0)
    user, _ = await _customer(session, SubscriptionStatus.ACTIVE, renews_at=soon)

    response, email = await _close(session, user)

    message = response.json()["data"]["message"]
    assert f"Your plan won't renew and stays active until {soon:%B %d, %Y}." in message
    assert "log back in before" not in message
    assert email.call_args.kwargs["log_back_in_by"] is None


@pytest.mark.asyncio
async def test_the_latest_end_of_every_running_plan_is_reported(session, provider):
    later = PAID_UNTIL + timedelta(days=200)
    user, _ = await _customer(session, SubscriptionStatus.ACTIVE)
    # An annual plan cancelled earlier, still paid through, beside the new one.
    session.add(
        UserSubscription(
            user_id=user.id,
            plan_id=(await session.execute(select(SubscriptionPlan.id).limit(1))).scalar_one(),
            status=SubscriptionStatus.CANCELLED,
            end_date=later,
        )
    )
    await session.flush()

    response, _ = await _close(session, user)

    assert response.status_code == 200, response.text
    assert datetime.fromisoformat(response.json()["data"]["plan_ends_at"]) == later


def test_the_email_says_until_when_the_plan_stays():
    from emails.templates.auth.account_recovery import create_account_deactivated_email

    with_plan = create_account_deactivated_email(user_name="Ana", plan_ends_on="October 23, 2026")
    without = create_account_deactivated_email(user_name="Ana")

    first_back = create_account_deactivated_email(
        user_name="Ana", plan_ends_on="November 30, 2026", log_back_in_by="October 20, 2026"
    )

    assert "stays active until <strong>October 23, 2026</strong>" in with_plan
    assert "the period you paid for" not in with_plan  # a free trial is no paid period
    assert "If you log back in before <strong>October 20, 2026</strong>" in first_back
    assert "won't renew" not in without
