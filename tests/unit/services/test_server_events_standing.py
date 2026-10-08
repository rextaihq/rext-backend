"""An event's standing read from the database: whose account is the team's own."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.server_events import read_event_context
from tests.conftest import TEST_DATABASE_URL


def _with_parents(*tables):
    """The tables, and every table their foreign keys reach."""
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


def _tables_for_an_unmigrated_database(sync, tables) -> None:
    """Make the tables on an empty test database only: a migrated one (CI's) is tested as
    its migrations built it."""
    if inspect(sync).has_table("alembic_version"):
        return
    Base.metadata.create_all(sync, tables=tables, checkfirst=True)


@pytest_asyncio.fixture
async def db():
    tables = _with_parents(
        Users.__table__,
        Role.__table__,
        UserRole.__table__,
        WorkspaceModel.__table__,
        SubscriptionPlan.__table__,
        UserSubscription.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(lambda sync: _tables_for_an_unmigrated_database(sync, tables))
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


async def _account(db, email=None) -> Users:
    user = Users(email=email or f"{uuid4().hex[:12]}@example.com")
    db.add(user)
    await db.flush()
    return user


async def _role(db, level: int, *, workspace_role: bool) -> Role:
    role = Role(
        name=f"role-{uuid4().hex[:8]}",
        display_name="A role",
        hierarchy_level=level,
        is_workspace_role=workspace_role,
    )
    db.add(role)
    await db.flush()
    return role


@pytest.mark.asyncio
@pytest.mark.parametrize("level", [80, 100])
async def test_an_admins_or_a_super_admins_account_is_the_teams(db, level):
    user = await _account(db)
    db.add(UserRole(user_id=user.id, role_id=(await _role(db, level, workspace_role=False)).id))
    await db.flush()

    assert (await read_event_context(db, user.id)).internal is True


@pytest.mark.asyncio
async def test_an_account_with_two_admin_roles_is_read_without_error(db):
    user = await _account(db)
    for level in (80, 100):
        role = await _role(db, level, workspace_role=False)
        db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.flush()

    assert (await read_event_context(db, user.id)).internal is True


@pytest.mark.asyncio
async def test_a_customer_who_owns_or_runs_a_workspace_is_not(db):
    """A customer's roles are inside their workspace and below an admin's level. Neither a
    high role inside a workspace nor a low one outside any makes an account the team's."""
    user = await _account(db)
    workspace = WorkspaceModel(user_id=user.id, name="Acme", slug=f"acme-{uuid4().hex[:8]}")
    db.add(workspace)
    await db.flush()
    owner = await _role(db, 60, workspace_role=True)
    inside_only = await _role(db, 100, workspace_role=True)
    support = await _role(db, 3, workspace_role=False)
    db.add_all(
        [
            UserRole(user_id=user.id, role_id=owner.id, workspace_id=workspace.id),
            UserRole(user_id=user.id, role_id=inside_only.id, workspace_id=workspace.id),
            UserRole(user_id=user.id, role_id=support.id),
        ]
    )
    await db.flush()

    assert (await read_event_context(db, user.id)).internal is False


@pytest.mark.asyncio
async def test_an_account_on_the_companys_domain_is_the_teams_with_no_role_at_all(db):
    team = await _account(db, email=f"it+{uuid4().hex[:8]}@revnix.com")
    customer = await _account(db)

    assert (await read_event_context(db, team.id)).internal is True
    assert (await read_event_context(db, customer.id)).internal is False


@pytest.mark.asyncio
async def test_an_account_that_is_gone_is_nobodys(db):
    context = await read_event_context(db, uuid4())

    assert (context.identified, context.internal, context.plan) == (False, False, {})
