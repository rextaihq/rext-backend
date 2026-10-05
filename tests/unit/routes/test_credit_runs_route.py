"""GET /api/v1/subscriptions/credits says what each billed button costs and leaves.

Checked on the test PostgreSQL: the tables the route reads are created inside a
transaction that is rolled back, so nothing is left behind.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[Users.__table__, SubscriptionPlan.__table__, UserSubscription.__table__],
                checkfirst=True,
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _credits(session, user_id):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user_id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/v1/subscriptions/credits")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.asyncio
async def test_the_balance_comes_with_each_button_s_cost_and_balance_after(session):
    plan = SubscriptionPlan(
        name=f"starter-{uuid4().hex[:8]}", display_name="Starter", credits_per_month=400
    )
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add_all([plan, user])
    await session.flush()
    session.add(
        UserSubscription(
            user_id=user.id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, current_credits=20
        )
    )
    await session.flush()

    data = await _credits(session, user.id)

    assert data["current_credits"] == 20
    assert data["articles_remaining"] == 1
    runs = data["runs"]
    assert runs["analyze"]["can_run"] is True and runs["analyze"]["balance_after"] == 19
    assert runs["generate"]["cost"] == 12 and runs["generate"]["balance_after"] == 8
    assert runs["change_keyword"]["balance_after"] == 18


@pytest.mark.asyncio
async def test_without_a_plan_no_button_can_run(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()

    data = await _credits(session, user.id)

    assert data["current_credits"] == 0
    assert all(run["can_run"] is False for run in data["runs"].values())
    assert all(run["balance_after"] is None for run in data["runs"].values())
