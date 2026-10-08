"""GET and PUT /api/v1/user/analytics-consent: the person's answer on usage analytics, stored on
their account (rext-control task 712), and what the server's events read from it.

Checked on the test PostgreSQL: the tables are created inside a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from src.services.server_events import EventContext, event_context
from tests.conftest import TEST_DATABASE_URL

URL = "/api/v1/user/analytics-consent"


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

        def tables_unless_migrated(sync):
            if not inspect(sync).has_table("alembic_version"):
                Base.metadata.create_all(
                    sync,
                    tables=_with_their_references([Users, UserRole, UserSubscription]),
                    checkfirst=True,
                )

        await connection.run_sync(tables_unless_migrated)
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def user(session):
    row = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(row)
    await session.flush()
    return row


@pytest_asyncio.fixture
async def client(session, user):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_an_account_starts_with_no_answer(client):
    response = await client.get(URL)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"answer": None, "region": None, "answered_at": None}


@pytest.mark.asyncio
async def test_an_answer_is_stored_with_its_region_and_its_time(client, user):
    response = await client.put(URL, json={"answer": "granted", "region": "eea"})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert (data["answer"], data["region"]) == ("granted", "eea")
    assert datetime.fromisoformat(data["answered_at"]) > datetime.now(timezone.utc) - timedelta(
        minutes=1
    )
    assert (user.analytics_consent, user.analytics_region) == ("granted", "eea")
    assert (await client.get(URL)).json()["data"] == data


@pytest.mark.asyncio
async def test_a_changed_answer_replaces_the_stored_one(client, user):
    await client.put(URL, json={"answer": "granted", "region": "other"})
    first = user.analytics_consent_at

    data = (await client.put(URL, json={"answer": "denied", "region": "other"})).json()["data"]

    assert data["answer"] == "denied"
    assert user.analytics_consent_at >= first


@pytest.mark.asyncio
async def test_the_same_answer_again_keeps_the_time_it_was_given(client, user):
    await client.put(URL, json={"answer": "denied", "region": "eea"})
    given = user.analytics_consent_at

    await client.put(URL, json={"answer": "denied", "region": "eea"})

    assert user.analytics_consent_at == given


@pytest.mark.asyncio
async def test_a_browser_with_no_answer_stores_its_region_and_undoes_no_refusal(client, user):
    """Outside the EEA nobody is asked, so the dashboard has a region and no answer to send. A
    browser that has forgotten a refusal sends the same: the refusal stays, and comes back."""
    data = (await client.put(URL, json={"answer": None, "region": "other"})).json()["data"]
    assert data == {"answer": None, "region": "other", "answered_at": None}

    await client.put(URL, json={"answer": "denied", "region": "other"})
    data = (await client.put(URL, json={"answer": None, "region": "eea"})).json()["data"]

    assert (data["answer"], data["region"]) == ("denied", "eea")
    assert user.analytics_consent == "denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"region": "eea"},
        {"answer": "granted"},
        {"answer": "maybe", "region": "eea"},
        {"answer": "granted", "region": "mars"},
        {"answer": "", "region": "eea"},
    ],
    ids=["no answer key", "no region", "another answer", "another region", "an empty answer"],
)
async def test_anything_but_the_two_answers_and_the_two_regions_is_refused(client, user, body):
    response = await client.put(URL, json=body)

    assert response.status_code == 422, response.text
    assert (user.analytics_consent, user.analytics_region) == (None, None)


@pytest.mark.asyncio
async def test_the_answer_is_not_part_of_a_users_card(user):
    user.analytics_consent, user.analytics_region = "denied", "eea"
    user.analytics_consent_at = datetime.now(timezone.utc)

    card = user.to_dict(include_nulls=True)

    assert not {"analytics_consent", "analytics_region", "analytics_consent_at"} & set(card)


@pytest.mark.asyncio
async def test_the_table_takes_no_other_value(session, user):
    user.analytics_consent = "perhaps"

    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_the_servers_events_read_the_stored_answer_and_the_plan(client, session, user):
    plan = SubscriptionPlan(
        name=f"growth-{uuid4().hex[:8]}", display_name="Growth", credits_per_month=400
    )
    session.add(plan)
    await session.flush()
    session.add(
        UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BillingPeriod.YEARLY,
            end_date=datetime.now(timezone.utc) + timedelta(days=20),
        )
    )
    await session.flush()
    standing = {"plan": plan.name, "plan_status": "active", "billing_period": "yearly"}

    # No answer and no region yet: anonymous.
    assert await event_context(session, user.id) == EventContext(identified=False, plan=standing)

    await client.put(URL, json={"answer": None, "region": "other"})
    assert (await event_context(session, user.id)).identified is True

    await client.put(URL, json={"answer": "denied", "region": "other"})
    assert (await event_context(session, user.id)).identified is False

    await client.put(URL, json={"answer": "granted", "region": "eea"})
    assert (await event_context(session, user.id)).identified is True


@pytest.mark.asyncio
async def test_an_account_that_isnt_there_has_no_context(session):
    assert await event_context(session, uuid4()) == EventContext()
