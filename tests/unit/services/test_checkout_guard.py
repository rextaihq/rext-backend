"""No second checkout while a subscription isn't finished (F11, revnix/rext-control#336).

A failed renewal is fixed with a new card, and a paused subscription, or a
cancelled one whose end hasn't come, is resumed: each is refused a new checkout
with the action to take instead, which /status reports for the dashboard. A
repeated checkout request reuses the open checkout, and /resume un-cancels a
cancelled subscription.

DB-backed tests create their tables inside a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.subscription_service as service_module
from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.exceptions import DuplicateResourceException, ResourceNotFoundException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.services.subscription_service import RESUME, UPDATE_PAYMENT_METHOD, billing_action
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
LATER, EARLIER = NOW + timedelta(days=10), NOW - timedelta(days=1)


def _row(status, *, ls_id="ls-1", end=None):
    return SimpleNamespace(status=status, lemonsqueezy_subscription_id=ls_id, end_date=end)


@pytest.mark.parametrize(
    ("row", "action"),
    [
        (_row(SubscriptionStatus.PAST_DUE), UPDATE_PAYMENT_METHOD),
        (_row(SubscriptionStatus.UNPAID), UPDATE_PAYMENT_METHOD),
        (_row(SubscriptionStatus.SUSPENDED), UPDATE_PAYMENT_METHOD),
        (_row(SubscriptionStatus.PAUSED), RESUME),
        (_row(SubscriptionStatus.CANCELLED, end=LATER), RESUME),
        # Ended, or not with Lemon Squeezy: nothing to resume.
        (_row(SubscriptionStatus.CANCELLED, end=EARLIER), None),
        (_row(SubscriptionStatus.CANCELLED, ls_id=None, end=LATER), None),
        (_row(SubscriptionStatus.EXPIRED), None),
        (_row(SubscriptionStatus.ACTIVE), None),
        (None, None),
    ],
)
def test_the_action_for_each_state(row, action):
    result = billing_action(row, NOW)

    assert (result["action"] if result else None) == action


READ_TABLES = [
    Users,
    SubscriptionPlan,
    UserSubscription,
    WorkspaceModel,
    WorkspaceMembers,  # /status's usage figures
    AuditLog,
]


def _with_their_references(models):
    """The tables and every table their foreign keys point at."""
    tables, stack = set(), [model.__table__ for model in models]
    while stack:
        table = stack.pop()
        if table not in tables:
            tables.add(table)
            stack.extend(fk.column.table for fk in table.foreign_keys)
    return list(tables)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=_with_their_references(READ_TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _user_with(db, status=None, *, end=None, ls_id="ls-guard"):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}",
        display_name="Growth",
        price_monthly=89,
        price_yearly=890,
        credits_per_month=1000,
        lemonsqueezy_variant_id_monthly=f"var-{uuid4().hex[:6]}",
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add_all([plan, user])
    await db.flush()
    if status is not None:
        db.add(
            UserSubscription(
                user_id=user.id,
                plan_id=plan.id,
                status=status,
                end_date=end,
                lemonsqueezy_subscription_id=f"{ls_id}-{uuid4().hex[:6]}",
            )
        )
        await db.flush()
    return user, plan


async def _checkout(service, user, plan):
    return await service.create_checkout(
        user_id=user.id,
        plan_id=plan.id,
        billing_period=BillingPeriod.MONTHLY,
        success_url="https://app.example.com/ok",
        cancel_url="https://app.example.com/cancel",
    )


@pytest.mark.parametrize(
    ("status", "end", "action", "says"),
    [
        (SubscriptionStatus.CANCELLED, LATER, RESUME, "Resume it"),
        (SubscriptionStatus.PAUSED, None, RESUME, "Resume it"),
        (SubscriptionStatus.UNPAID, None, UPDATE_PAYMENT_METHOD, "couldn't be collected"),
    ],
)
@pytest.mark.asyncio
async def test_an_unfinished_subscription_gets_its_action_not_a_checkout(
    session, status, end, action, says
):
    user, plan = await _user_with(session, status, end=end)
    service = service_module.SubscriptionService(session)

    with pytest.raises(DuplicateResourceException) as refused:
        await _checkout(service, user, plan)

    assert refused.value.context["billing_action"] == action
    assert says in refused.value.message


@pytest.mark.asyncio
async def test_an_ended_cancellation_may_check_out_again(session):
    user, _ = await _user_with(session, SubscriptionStatus.CANCELLED, end=EARLIER)
    service = service_module.SubscriptionService(session)

    # Past the guard: the made-up plan id is what stops it.
    with pytest.raises(ResourceNotFoundException):
        await service.create_checkout(
            user_id=user.id,
            plan_id=uuid4(),
            billing_period=BillingPeriod.MONTHLY,
            success_url="https://app.example.com/ok",
            cancel_url="https://app.example.com/cancel",
        )


@pytest.mark.asyncio
async def test_a_repeated_checkout_reuses_the_open_one(session, monkeypatch):
    user, plan = await _user_with(session)
    store = {}

    async def cache_get(key):
        return store.get(key)

    async def cache_set(key, value, ttl=300):
        store[key] = value
        return True

    monkeypatch.setattr(service_module.cache, "get", cache_get)
    monkeypatch.setattr(service_module.cache, "set", cache_set)
    service = service_module.SubscriptionService(session)
    provider = SimpleNamespace(
        create_customer=AsyncMock(return_value="cus_1"),
        create_checkout_session=AsyncMock(
            return_value=SimpleNamespace(
                checkout_url="https://checkout.example/1", session_id="sess-1"
            )
        ),
    )
    monkeypatch.setattr(service, "payment_provider", provider)

    first = await _checkout(service, user, plan)
    second = await _checkout(service, user, plan)

    assert first == second == {"checkout_url": "https://checkout.example/1", "session_id": "sess-1"}
    provider.create_checkout_session.assert_awaited_once()


async def _call(session, user_id, method, path):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user_id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(method, f"/api/v1/subscriptions{path}")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("status", "call"),
    [
        (SubscriptionStatus.CANCELLED, "uncancel_subscription"),
        (SubscriptionStatus.PAUSED, "resume_subscription"),
    ],
)
@pytest.mark.asyncio
async def test_resume_un_cancels_a_cancelled_subscription(session, status, call):
    from src.api.routes.subscriptions import subscription_routes

    user, _ = await _user_with(session, status, end=LATER)
    provider = SimpleNamespace(uncancel_subscription=AsyncMock(), resume_subscription=AsyncMock())

    with patch.object(subscription_routes, "get_payment_provider_singleton", lambda: provider):
        response = await _call(session, user.id, "POST", "/resume")

    assert response.status_code == 200, response.text
    getattr(provider, call).assert_awaited_once()
    other = "resume_subscription" if call == "uncancel_subscription" else "uncancel_subscription"
    getattr(provider, other).assert_not_called()


@pytest.mark.asyncio
async def test_status_reports_the_action_for_the_dashboard(session):
    from src.api.routes.subscriptions import subscription_routes

    user, _ = await _user_with(session, SubscriptionStatus.UNPAID)

    with (
        patch.object(
            subscription_routes.SubscriptionService,
            "get_customer_portal_url",
            AsyncMock(return_value=None),
        ),
        # The usage figures read the knowledge tables; they aren't what's checked here.
        patch.object(
            subscription_routes.UsageTrackingService,
            "get_usage_metrics",
            AsyncMock(return_value={}),
        ),
    ):
        response = await _call(session, user.id, "GET", "/status")

    assert response.status_code == 200, response.text
    action = response.json()["data"]["billing_action"]
    assert action["action"] == UPDATE_PAYMENT_METHOD
    assert action["status"] == "unpaid"
