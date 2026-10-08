"""An impersonated session ends when it could no longer be started (revnix/rext-control#940).

Starting one is checked once. The session it gives is then asked on every request
whether it may go on: not stopped, and the account that started it still active, still
holding user.impersonate and still above the account it acts as. Checked on the test
PostgreSQL inside a rolled-back transaction, with one token that never changes.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import RextAuthenticationException
from src.api.models.user_models.impersonation_session import ImpersonationSession
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import _ensure_active_user_session
from src.services.impersonation_service import ImpersonationService
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
        ImpersonationSession.__table__,
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


async def _role(db, level: int, *, may_impersonate: bool) -> Role:
    """A role of its own at that level, with or without user.impersonate."""
    role = Role(name=f"role_{uuid4().hex[:10]}", display_name="A role", hierarchy_level=level)
    db.add(role)
    await db.flush()
    if may_impersonate:
        found = await db.execute(select(Permission).where(Permission.name == "user.impersonate"))
        permission = found.scalar_one_or_none()
        if permission is None:
            permission = Permission(
                name="user.impersonate",
                display_name="Impersonate Users",
                resource="user",
                action="impersonate",
            )
            db.add(permission)
            await db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
        await db.flush()
    return role


async def _account(db, *roles: Role) -> Users:
    user = Users(email=f"{uuid4().hex[:12]}@example.com", email_verified=True, status="active")
    db.add(user)
    await db.flush()
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    await db.flush()
    return user


async def _take(db, user, role) -> None:
    await db.execute(
        delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    await db.flush()


def _token(admin, customer) -> dict:
    """What an impersonation's access token says, from its start to its end."""
    return {
        "id": str(customer.id),
        "is_impersonating": True,
        "original_user_id": str(admin.id),
        "session_id": str(uuid4()),
        "session_kind": "impersonation",
    }


async def _goes_on(db, token) -> bool:
    try:
        await _ensure_active_user_session(token, db)
    except RextAuthenticationException as refused:
        assert "impersonation session has ended" in refused.message
        return False
    return True


@pytest_asyncio.fixture
async def started(session):
    """An admin acting as a customer: (the admin, its role, the customer, the token)."""
    role = await _role(session, 80, may_impersonate=True)
    admin = await _account(session, role)
    customer = await _account(session)
    return admin, role, customer, _token(admin, customer)


async def test_it_goes_on_while_the_admin_holds_the_role_and_ends_when_it_is_taken_away(
    session, started
):
    admin, role, _, token = started
    assert await _goes_on(session, token) is True

    await _take(session, admin, role)

    assert await _goes_on(session, token) is False


@pytest.mark.parametrize("status", ["suspended", "banned"])
async def test_it_ends_when_the_admin_is_suspended_or_banned(session, started, status):
    admin, _, _, token = started
    admin.status = status
    await session.flush()

    assert await _goes_on(session, token) is False


async def test_it_ends_when_the_admins_account_is_gone(session, started):
    admin, role, _, token = started
    await _take(session, admin, role)
    await session.execute(delete(Users).where(Users.id == admin.id))
    await session.flush()

    assert await _goes_on(session, token) is False


async def test_it_ends_when_the_admin_no_longer_outranks_the_account(session, started):
    """Still allowed to impersonate, but not this account any more."""
    admin, role, customer, token = started
    lower = await _role(session, 60, may_impersonate=True)
    session.add(UserRole(user_id=admin.id, role_id=lower.id))
    session.add(UserRole(user_id=customer.id, role_id=lower.id))
    await session.flush()
    assert await _goes_on(session, token) is True

    await _take(session, admin, role)

    assert await _goes_on(session, token) is False


async def test_it_ends_when_it_is_stopped(session, started):
    """Stopping records the session as ended; its token is refused from then on."""
    _, _, _, token = started

    assert await ImpersonationService(session).invalidate_session(token["session_id"]) is True

    assert await _goes_on(session, token) is False


async def test_the_permission_held_through_two_roles_is_one_answer(session, started):
    """Asking for "the one row" raised for such an account, at the start too."""
    admin, _, customer, token = started
    session.add(
        UserRole(user_id=admin.id, role_id=(await _role(session, 100, may_impersonate=True)).id)
    )
    await session.flush()

    assert await ImpersonationService(session)._has_impersonation_permission(admin.id) is True
    assert await _goes_on(session, token) is True
    context = await ImpersonationService(session).start_impersonation(admin.id, customer.id)
    assert context["target_user_id"] == str(customer.id)


async def test_the_permission_held_only_inside_a_workspace_is_not_enough(session):
    role = await _role(session, 80, may_impersonate=True)
    admin, customer = await _account(session), await _account(session)
    workspace = WorkspaceModel(name="Acme", slug=f"acme-{uuid4().hex[:8]}", user_id=admin.id)
    session.add(workspace)
    await session.flush()
    session.add(UserRole(user_id=admin.id, role_id=role.id, workspace_id=workspace.id))
    await session.flush()

    assert await ImpersonationService(session)._has_impersonation_permission(admin.id) is False
    assert await _goes_on(session, _token(admin, customer)) is False


async def test_a_session_of_ones_own_is_not_asked_any_of_this(session):
    """A token that isn't an impersonation's passes as before, with no admin named."""
    customer = await _account(session)

    await _ensure_active_user_session({"id": str(customer.id), "session_kind": "legacy"}, session)


async def test_an_impersonation_token_that_names_no_admin_is_refused(session):
    customer = await _account(session)

    with pytest.raises(RextAuthenticationException):
        await _ensure_active_user_session(
            {"id": str(customer.id), "is_impersonating": True, "session_kind": "impersonation"},
            session,
        )
