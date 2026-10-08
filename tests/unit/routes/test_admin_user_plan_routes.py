"""The admin plan routes (FB2.29, revnix/rext-control#710).

GET /api/v1/admin/users/{user_id}/plan and the two POSTs beside it (plan, trial) are a
super admin's; a change needs billing.manage too, and is never made on a Super Admin's
account. Checked on the test PostgreSQL inside a rolled-back transaction: the route's
commits and rollbacks act on a savepoint inside it. The roles, Lemon Squeezy and the
cache are stubbed under the real guards.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.admin_plan_changes as plan_changes_module
import src.services.subscription_service as subscription_service_module
from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from src.services.subscription_service import SubscriptionService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)
REASON = "Moved up as agreed on the call"


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
    tables = _with_parents(UserSubscription.__table__, AuditLog.__table__)
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()

        def tables_unless_migrated(sync):
            if not inspect(sync).has_table("alembic_version"):
                Base.metadata.create_all(sync, tables=tables, checkfirst=True)

        await connection.run_sync(tables_unless_migrated)
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def lemon(monkeypatch):
    provider = MagicMock(
        update_subscription=AsyncMock(
            side_effect=lambda **sent: SimpleNamespace(plan_id=sent["price_id"])
        )
    )
    monkeypatch.setattr(
        subscription_service_module, "get_payment_provider_singleton", lambda: provider
    )
    monkeypatch.setattr(subscription_service_module, "invalidate_cache", AsyncMock(return_value=0))
    monkeypatch.setattr(plan_changes_module, "invalidate_cache", AsyncMock(return_value=0))
    monkeypatch.setattr(
        SubscriptionService,
        "calculate_usage",
        AsyncMock(return_value={"workspaces": 0, "members": 0}),
    )
    return provider


async def _user(db) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _plan(db, name, *, price, credits, trial=False):
    tag = uuid4().hex[:8]
    plan = SubscriptionPlan(
        name=f"{name}-{tag}",
        display_name=name.title(),
        price_monthly=Decimal(price),
        price_yearly=Decimal(price) * 10,
        credits_per_month=credits,
        is_trial_plan=trial,
        lemonsqueezy_variant_id_monthly=None if trial else f"v-{name}-m-{tag}",
        lemonsqueezy_variant_id_yearly=None if trial else f"v-{name}-y-{tag}",
    )
    db.add(plan)
    await db.flush()
    return plan


async def _customer(db, plan, *, left=100) -> tuple[Users, UserSubscription]:
    user = await _user(db)
    row = UserSubscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        billing_period=BillingPeriod.MONTHLY,
        lemonsqueezy_subscription_id=f"ls-{uuid4().hex[:8]}",
        start_date=NOW - timedelta(days=10),
        renews_at=NOW + timedelta(days=20),
        credits_reset_date=NOW + timedelta(days=20),
        current_credits=left,
        subscription_metadata={"start_month_given": True},
    )
    db.add(row)
    await db.flush()
    return user, row


async def _trial_user(db) -> tuple[Users, UserSubscription]:
    trial = await _plan(db, "trial", price=0, credits=60, trial=True)
    user = await _user(db)
    end = NOW + timedelta(days=2)
    row = UserSubscription(
        user_id=user.id,
        plan_id=trial.id,
        status=SubscriptionStatus.TRIAL,
        billing_period=BillingPeriod.MONTHLY,
        start_date=NOW - timedelta(days=5),
        trial_end_date=end,
        end_date=end,
        credits_reset_date=end,
        current_credits=40,
        subscription_metadata={},
    )
    db.add(row)
    await db.flush()
    return user, row


@pytest.fixture
def call(session, monkeypatch):
    """call(caller, method, url, json=None, *, super_admins=(), permissions=()) -> response."""
    from src.api.server import app

    async def override_db():
        yield session

    async def _call(caller, method, url, json=None, *, super_admins=(), permissions=()):
        admins = {u.id for u in super_admins}
        monkeypatch.setattr(
            "src.utils.rbac_utils.is_user_super_admin",
            AsyncMock(side_effect=lambda db, user_id: user_id in admins),
        )
        monkeypatch.setattr(
            "src.utils.rbac_utils.get_user_permissions",
            AsyncMock(return_value=list(permissions)),
        )
        app.dependency_overrides[get_async_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: {
            "identity": str(caller.id),
            "roles": [],
        }
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                return await ac.request(method, url, json=json)
        finally:
            app.dependency_overrides.clear()

    return _call


def _url(user, what="plan") -> str:
    return f"/api/v1/admin/users/{user.id}/{what}"


def _change(plan, **fields) -> dict:
    return {
        "plan_id": str(plan.id),
        "billing_period": "monthly",
        "billing": "next_renewal",
        "reason": REASON,
        **fields,
    }


async def test_a_super_admin_reads_what_a_users_plan_can_become(session, call, lemon):
    starter = await _plan(session, "starter", price=39, credits=400)
    growth = await _plan(session, "growth", price=89, credits=1000)
    customer, row = await _customer(session, starter)
    admin = await _user(session)

    response = await call(admin, "GET", _url(customer), super_admins=[admin])

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["currency"] == "USD"
    assert data["subscription"]["plan_id"] == str(starter.id)
    assert data["subscription"]["monthly_credits"] == 100
    assert data["change"] == {
        "allowed": True,
        "refused_reason": None,
        "default_billing": "next_renewal",
    }
    assert data["limits"] == {"reason_min": 3, "reason_max": 500}
    (to_growth,) = [p for p in data["plans"] if p["id"] == str(growth.id)]
    assert to_growth["price_monthly"] == "89.00"
    monthly = to_growth["periods"][0]
    assert (monthly["billing_period"], monthly["kind"], monthly["allowed"]) == (
        "monthly",
        "upgrade",
        True,
    )
    assert monthly["modes"] == [
        {"billing": "next_renewal", "plan_changes": "now", "monthly_credits_after": 700},
        {"billing": "charge_now", "plan_changes": "now", "monthly_credits_after": 700},
    ]


async def test_a_super_admin_changes_a_users_plan(session, call, lemon):
    starter = await _plan(session, "starter", price=39, credits=400)
    growth = await _plan(session, "growth", price=89, credits=1000)
    customer, row = await _customer(session, starter)
    admin = await _user(session)

    response = await call(admin, "POST", _url(customer), _change(growth), super_admins=[admin])

    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["old_plan"]["id"], data["new_plan"]["id"]) == (str(starter.id), str(growth.id))
    assert (data["billing"], data["monthly_credits_after"]) == ("next_renewal", 700)
    await session.refresh(row)
    assert (row.plan_id, row.current_credits) == (growth.id, 700)
    entry = await session.get(AuditLog, data["audit_id"])
    assert (entry.action, entry.user_id) == ("admin.plan_changed", customer.id)
    lemon.update_subscription.assert_awaited_once()


async def test_a_change_that_cant_be_saved_after_lemon_squeezy_took_it_alerts_a_person(
    session, call, lemon, monkeypatch
):
    """The commit fails after Lemon Squeezy accepted: neither the plan nor the audit entry is
    here, so who changed it and why goes to a person before the error goes on."""
    import src.api.routes.admin.user_plan_routes as routes_module

    starter = await _plan(session, "starter", price=39, credits=400)
    growth = await _plan(session, "growth", price=89, credits=1000)
    customer, _ = await _customer(session, starter)
    admin = await _user(session)
    alert = MagicMock()
    monkeypatch.setattr(routes_module, "trigger_payment_alert", alert)
    monkeypatch.setattr(session, "commit", AsyncMock(side_effect=RuntimeError("connection lost")))

    response = await call(admin, "POST", _url(customer), _change(growth), super_admins=[admin])

    assert response.status_code >= 500
    lemon.update_subscription.assert_awaited_once()
    told = alert.call_args.kwargs
    assert told["alert_type"] == "admin_plan_change_unrecorded"
    assert told["user_id"] == str(customer.id)
    assert (told["context"]["old_plan"], told["context"]["new_plan"]) == (
        starter.name,
        growth.name,
    )
    assert told["context"]["admin"] == str(admin.id)


async def test_a_super_admin_moves_a_trials_end(session, call, lemon):
    customer, row = await _trial_user(session)
    admin = await _user(session)
    later = NOW + timedelta(days=9)

    options = await call(admin, "GET", _url(customer), super_admins=[admin])
    response = await call(
        admin,
        "POST",
        _url(customer, "trial"),
        {"ends_at": later.isoformat(), "reason": "A week more to try it"},
        super_admins=[admin],
    )

    standing = options.json()["data"]
    assert standing["change"]["allowed"] is False
    assert standing["trial_extension"]["allowed"] is True
    assert response.status_code == 200
    await session.refresh(row)
    assert row.trial_end_date == later
    assert (
        await session.execute(select(AuditLog.action).where(AuditLog.user_id == customer.id))
    ).scalars().all() == ["admin.trial_extended"]


@pytest.mark.parametrize("method_and_path", [("GET", "plan"), ("POST", "plan"), ("POST", "trial")])
async def test_only_a_super_admin_reaches_the_plan_routes(session, call, lemon, method_and_path):
    method, path = method_and_path
    starter = await _plan(session, "starter", price=39, credits=400)
    customer, row = await _customer(session, starter)
    support = await _user(session)
    body = {
        "GET": None,
        "plan": _change(starter),
        "trial": {"ends_at": (NOW + timedelta(days=9)).isoformat(), "reason": REASON},
    }["GET" if method == "GET" else path]

    response = await call(
        support,
        method,
        _url(customer, path),
        body,
        permissions=["billing.read", "billing.manage"],
    )

    assert response.status_code == 403
    assert row.plan_id == starter.id


async def test_a_super_admins_own_kind_is_never_the_target(session, call, lemon):
    starter = await _plan(session, "starter", price=39, credits=400)
    growth = await _plan(session, "growth", price=89, credits=1000)
    other_admin, row = await _customer(session, starter)
    admin = await _user(session)

    # The options say so first, so the dashboard offers nothing it would be refused.
    options = await call(admin, "GET", _url(other_admin), super_admins=[admin, other_admin])
    response = await call(
        admin, "POST", _url(other_admin), _change(growth), super_admins=[admin, other_admin]
    )

    data = options.json()["data"]
    assert data["change"]["allowed"] is False
    assert "Super Admin" in data["change"]["refused_reason"]
    assert data["trial_extension"]["allowed"] is False
    assert response.status_code in (400, 403)
    assert row.plan_id == starter.id
    lemon.update_subscription.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        {"billing_period": "lifetime"},
        {"billing": "free"},
        {"plan_id": "not-a-plan"},
        {"reason": None},
    ],
)
async def test_a_body_the_change_cannot_take_is_refused(session, call, lemon, body):
    starter = await _plan(session, "starter", price=39, credits=400)
    growth = await _plan(session, "growth", price=89, credits=1000)
    customer, row = await _customer(session, starter)
    admin = await _user(session)

    response = await call(
        admin, "POST", _url(customer), {**_change(growth), **body}, super_admins=[admin]
    )

    assert response.status_code == 422
    assert row.plan_id == starter.id


async def test_a_refusal_says_that_nothing_was_changed(session, call, lemon):
    starter = await _plan(session, "starter", price=39, credits=400)
    customer, row = await _customer(session, starter)
    admin = await _user(session)

    response = await call(admin, "POST", _url(customer), _change(starter), super_admins=[admin])

    assert response.status_code == 400
    assert "Nothing was changed" in response.text
    lemon.update_subscription.assert_not_awaited()


async def test_an_unknown_user_is_not_found(session, call, lemon):
    admin = await _user(session)
    ghost = Users(id=uuid4(), email="ghost@example.com")

    response = await call(admin, "GET", _url(ghost), super_admins=[admin])

    assert response.status_code == 404


async def test_the_users_list_carries_each_rows_plan(session, call, lemon, monkeypatch):
    # GET /api/v1/user/users is the list the dashboard's Admin > Users page reads.
    growth = await _plan(session, "growth", price=89, credits=1000)
    paying, _ = await _customer(session, growth)
    trying, _ = await _trial_user(session)
    nobody = await _user(session)
    admin = await _user(session)

    def row(user):
        return SimpleNamespace(
            id=user.id,
            to_dict=lambda: {
                "id": str(user.id),
                "email": user.email,
                "status": "active",
                "email_verified": True,
                "created_at": NOW.isoformat(),
            },
        )

    page = {"page": 1, "per_page": 50, "total": 3, "total_pages": 1}
    monkeypatch.setattr(
        "src.api.routes.users.management.UserService.get_users",
        AsyncMock(
            return_value={
                "users": [row(paying), row(trying), row(nobody)],
                "pagination": {**page, "has_next": False, "has_prev": False},
            }
        ),
    )

    response = await call(
        admin, "GET", "/api/v1/user/users", super_admins=[admin], permissions=["user.manage"]
    )

    assert response.status_code == 200
    rows = {r["id"]: r for r in response.json()["data"]["users"]}
    plan = ("plan_display_name", "is_trial", "billing_period")
    assert [rows[str(paying.id)][k] for k in plan] == ["Growth", False, "monthly"]
    assert [rows[str(trying.id)][k] for k in plan] == ["Trial", True, "monthly"]
    assert [rows[str(nobody.id)][k] for k in plan] == [None, False, None]
