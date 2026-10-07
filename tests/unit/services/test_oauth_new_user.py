"""OAuth login says whether it created the account (C13a, revnix/rext-control#583).

The dashboard counts a sign-up through Google or GitHub only when the backend created the account,
not when an existing person signs in through the same button. Checked on the test PostgreSQL
inside a rolled-back transaction, with no trial plan seeded (so no trial or credits are granted).
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.services.oauth_service import OAuthService
from tests.conftest import TEST_DATABASE_URL

TABLES = [
    Users,
    OAuthAccount,
    UserSession,
    UserRole,
    Permission,
    RolePermission,
    SubscriptionPlan,
    UserSubscription,
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
                sync, tables=_with_their_references(TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


def _login(service: OAuthService, account_id: str, email: str):
    return service.oauth_login_or_register(
        provider="google",
        provider_account_id=account_id,
        provider_email=email,
        provider_name="Sam Rivera",
    )


@pytest.mark.asyncio
async def test_the_first_login_creates_the_account_and_says_so(session):
    email = f"sam-{uuid4().hex[:8]}@acme-corp.io"
    service = OAuthService(session)

    user, tokens = await _login(service, f"g-{uuid4().hex}", email)

    assert user.email == email
    assert tokens["is_new_user"] is True


@pytest.mark.asyncio
async def test_a_later_login_through_the_same_account_is_not_a_sign_up(session):
    account_id, email = f"g-{uuid4().hex}", f"sam-{uuid4().hex[:8]}@acme-corp.io"
    service = OAuthService(session)
    first, _ = await _login(service, account_id, email)

    again, tokens = await _login(service, account_id, email)

    assert again.id == first.id
    assert tokens["is_new_user"] is False


@pytest.mark.asyncio
async def test_linking_google_to_an_existing_account_is_not_a_sign_up(session):
    email = f"sam-{uuid4().hex[:8]}@acme-corp.io"
    existing = Users(email=email, full_name="Sam Rivera", email_verified=True)
    session.add(existing)
    await session.flush()

    user, tokens = await _login(OAuthService(session), f"g-{uuid4().hex}", email)

    assert user.id == existing.id
    assert tokens["is_new_user"] is False
