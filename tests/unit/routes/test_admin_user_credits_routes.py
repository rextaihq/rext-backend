"""The admin credit routes and the customer's credit history (FB2.28, revnix/rext-control#709).

POST and GET /api/v1/admin/users/{user_id}/credits are a super admin's (a change needs
billing.manage too, and never on a Super Admin's account); GET
/api/v1/subscriptions/credits/history is the customer's own, naming Rext support only.
Checked on the test PostgreSQL inside a rolled-back transaction: the route's commits
and rollbacks act on a savepoint inside it. The roles are stubbed under the real
guards.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.credit_grants import CreditGrant
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.promotions import Promotion
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)
REASON = "Compensation for the outage"


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
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _user(db) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _customer(db, credits=600) -> Users:
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=1000
    )
    db.add(plan)
    user = await _user(db)
    db.add(
        UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            start_date=NOW - timedelta(days=10),
            current_credits=credits,
            credits_reset_date=NOW + timedelta(days=20),
            subscription_metadata={},
        )
    )
    await db.flush()
    return user


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


def _credits_url(user) -> str:
    return f"/api/v1/admin/users/{user.id}/credits"


@pytest.mark.asyncio
async def test_a_super_admin_adds_credits(session, call):
    customer = await _customer(session)
    admin = await _user(session)

    response = await call(
        admin,
        "POST",
        _credits_url(customer),
        {"action": "add", "amount": 150, "reason": REASON},
        super_admins=[admin],
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert (data["action"], data["amount"]) == ("add", 150)
    assert (data["balance_before"], data["balance_after"]) == (600, 750)
    grant = await session.get(CreditGrant, data["grant_id"])
    assert (grant.source, grant.remaining, grant.granted_by) == ("admin", 150, admin.id)


@pytest.mark.asyncio
async def test_without_billing_manage_the_change_is_refused(session, call):
    customer = await _customer(session)
    caller = await _user(session)

    response = await call(
        caller,
        "POST",
        _credits_url(customer),
        {"action": "add", "amount": 150, "reason": REASON},
        permissions=["billing.read"],
    )

    assert response.status_code == 403
    assert "You do not have permission" in response.text


@pytest.mark.asyncio
async def test_billing_manage_without_the_super_admin_role_is_refused(session, call):
    customer = await _customer(session)
    caller = await _user(session)

    response = await call(
        caller,
        "POST",
        _credits_url(customer),
        {"action": "add", "amount": 150, "reason": REASON},
        permissions=["billing.manage", "billing.read"],
    )

    assert response.status_code == 403
    assert "Super admin role required" in response.text
    assert (await session.execute(select(CreditGrant))).scalars().all() == []


@pytest.mark.asyncio
async def test_a_super_admins_credits_are_not_changed_here(session, call):
    admin = await _customer(session)

    response = await call(
        admin,
        "POST",
        _credits_url(admin),
        {"action": "add", "amount": 150, "reason": REASON},
        super_admins=[admin],
    )

    assert response.status_code == 403
    assert "Super Admin accounts are protected" in response.text


@pytest.mark.asyncio
async def test_an_unknown_user_is_not_found(session, call):
    admin = await _user(session)

    response = await call(
        admin,
        "POST",
        f"/api/v1/admin/users/{uuid4()}/credits",
        {"action": "add", "amount": 150, "reason": REASON},
        super_admins=[admin],
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"action": "reset", "amount": 10, "reason": REASON},
        {"action": "add", "reason": REASON},
        {"action": "add", "amount": 10, "reason": "  "},
        {"action": "add", "amount": 10, "reason": REASON, "expires_at": "2020-01-01T00:00:00Z"},
        {"action": "add", "amount": True, "reason": REASON},  # not read as 1 credit
    ],
)
async def test_a_body_the_action_does_not_take_is_refused(session, call, body):
    customer = await _customer(session)
    admin = await _user(session)

    response = await call(admin, "POST", _credits_url(customer), body, super_admins=[admin])

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_admin_reads_the_breakdown_and_the_history(session, call):
    customer = await _customer(session)
    admin = await _user(session)
    await call(
        admin,
        "POST",
        _credits_url(customer),
        {"action": "add", "amount": 150, "reason": REASON},
        super_admins=[admin],
    )
    await call(
        admin,
        "POST",
        _credits_url(customer),
        {"action": "deduct", "amount": 200, "reason": "Added twice by mistake"},
        super_admins=[admin],
    )

    response = await call(admin, "GET", _credits_url(customer), super_admins=[admin])

    assert response.status_code == 200
    data = response.json()["data"]
    credits = data["credits"]
    assert (credits["current_credits"], credits["monthly_credits"]) == (550, 550)
    assert credits["added_credits"] is None  # all 150 taken back
    assert credits["period_adjustment"] == -50
    # The form's limits come with the read, so the dashboard holds no copy of them.
    assert data["limits"] == {"amount_max": 100_000, "reason_min": 3, "reason_max": 500}
    [grant] = data["grants"]
    assert (grant["remaining"], grant["forfeited"], grant["reason"]) == (0, 150, REASON)
    assert (grant["granted_by"], grant["granted_by_email"]) == (str(admin.id), admin.email)
    assert [a["action"] for a in data["adjustments"]] == ["deduct", "add"]
    assert data["adjustments"][0]["adjusted_by_email"] == admin.email


@pytest.mark.asyncio
async def test_reading_a_users_credits_needs_the_super_admin_role(session, call):
    customer = await _customer(session)
    caller = await _user(session)

    response = await call(caller, "GET", _credits_url(customer), permissions=["billing.read"])

    assert response.status_code == 403
    assert "Super admin role required" in response.text


@pytest.mark.asyncio
async def test_the_customer_sees_the_change_and_rext_support_only(session, call):
    customer = await _customer(session)
    admin = await _user(session)
    await call(
        admin,
        "POST",
        _credits_url(customer),
        {
            "action": "add",
            "amount": 150,
            "reason": REASON,
            "expires_at": (NOW + timedelta(days=10)).isoformat(),
        },
        super_admins=[admin],
    )

    history = await call(customer, "GET", "/api/v1/subscriptions/credits/history")
    balance = await call(customer, "GET", "/api/v1/subscriptions/credits")

    assert history.status_code == 200
    data = history.json()["data"]
    [grant] = data["grants"]
    assert (grant["amount"], grant["reason"], grant["granted_by"]) == (150, REASON, "Rext support")
    [entry] = data["adjustments"]
    assert (entry["action"], entry["adjusted_by"]) == ("add", "Rext support")
    assert entry["grant_id"] == grant["id"]  # the add and its grant are one change
    assert str(admin.id) not in history.text and admin.email not in history.text
    credits = balance.json()["data"]
    assert credits["current_credits"] == 750
    assert credits["added_credits"]["credits"] == 150
    assert credits["bonus"] is None
