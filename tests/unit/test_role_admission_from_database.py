"""A route that admits a role by its name asks the database (revnix/rext-control#932).

`require_permissions(..., allow_roles=(...))` decides from the roles the account holds
outside any workspace, as the guard's other checks do, so a role given or taken away
counts from that moment. Checked on the test PostgreSQL inside a rolled-back transaction,
with the guard's real checks and a caller whose token never changes.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.rbac_utils import holds_global_role
from src.utils.route_decorators import require_permissions
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio


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
        Users.__table__,
        Role.__table__,
        UserRole.__table__,
        Permission.__table__,
        RolePermission.__table__,
        WorkspaceModel.__table__,
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


async def _role(db, name: str, *, workspace_role: bool = False) -> Role:
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(
            name=name,
            display_name=name.title(),
            hierarchy_level=3,
            is_workspace_role=workspace_role,
        )
        db.add(role)
        await db.flush()
    return role


async def _account(db) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com", email_verified=True)
    db.add(user)
    await db.flush()
    return user


async def _give(db, user, role, workspace_id=None, *, primary=True) -> None:
    db.add(
        UserRole(user_id=user.id, role_id=role.id, workspace_id=workspace_id, is_primary=primary)
    )
    await db.flush()


async def _take(db, user, role) -> None:
    await db.execute(
        delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    await db.flush()


@require_permissions("user.manage", allow_roles=("support",))
async def _users_page(*, current_user, db):
    return "the page"


async def _opens(db, user, token_roles) -> bool:
    """Whether the guard lets this caller in. The caller is as its token describes it."""
    try:
        return (
            await _users_page(
                current_user={"identity": str(user.id), "roles": list(token_roles)}, db=db
            )
        ) == "the page"
    except RextAuthorizationException:
        return False


async def test_a_role_counts_from_the_moment_it_is_given_and_until_it_is_taken_away(session):
    """One caller, one token that never changes."""
    support = await _role(session, "support")
    account = await _account(session)

    assert await _opens(session, account, token_roles=[]) is False

    await _give(session, account, support)
    assert await _opens(session, account, token_roles=[]) is True

    await _take(session, account, support)
    assert await _opens(session, account, token_roles=[]) is False


async def test_a_token_that_still_names_the_role_opens_nothing(session):
    """The role was taken away, or never held: what the token says doesn't count."""
    support = await _role(session, "support")
    account = await _account(session)
    await _give(session, account, support)
    await _take(session, account, support)

    assert await _opens(session, account, token_roles=["support"]) is False
    assert await _opens(session, await _account(session), token_roles=["support"]) is False


async def test_only_a_role_held_outside_any_workspace_matches(session):
    support = await _role(session, "support")
    other = await _role(session, f"helper_{uuid4().hex[:8]}")
    account, owner = await _account(session), await _account(session)
    workspace = WorkspaceModel(name="Acme", slug=f"acme-{uuid4().hex[:8]}", user_id=owner.id)
    session.add(workspace)
    await session.flush()

    # The same name held inside a workspace, and another role held globally: neither.
    await _give(session, account, support, workspace.id)
    await _give(session, account, other)
    assert await holds_global_role(session, account.id, ("support",)) is False
    assert await _opens(session, account, token_roles=[]) is False

    # Held globally, in a row that isn't the primary one: held is held, as for permissions.
    await _give(session, account, support, primary=False)
    assert await holds_global_role(session, account.id, ("support",)) is True
    assert await holds_global_role(session, account.id, ("admin", "support")) is True
    assert await holds_global_role(session, account.id, ("admin",)) is False
    assert await holds_global_role(session, account.id, ()) is False
    assert await _opens(session, account, token_roles=[]) is True


async def test_a_route_that_names_no_role_is_decided_by_the_permission_alone(session):
    support = await _role(session, "support")
    account = await _account(session)
    await _give(session, account, support)

    @require_permissions("user.manage")
    async def _write(*, current_user, db):
        return "done"

    with pytest.raises(RextAuthorizationException):
        await _write(current_user={"identity": str(account.id), "roles": ["support"]}, db=session)
