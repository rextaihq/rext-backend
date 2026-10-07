"""GET /api/v1/workspaces/{workspace}/personas says how many articles each persona wrote.

The dashboard's persona table shows it. Trashed articles and other workspaces' articles don't
count, and a persona that wrote nothing says 0. Checked on the test PostgreSQL: the tables the
route reads are created inside a transaction that is rolled back.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

# UserRole: the route's workspace lookup asks whether the caller is a super admin.
READ_TABLES = [WorkspaceModel, WorkspaceMembers, Content, Persona, UserRole]


def _with_their_references(models):
    """The route's tables and every table their foreign keys point at."""
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


async def _workspace(session, user, name):
    workspace = WorkspaceModel(user_id=user.id, name=name, slug=f"{name}-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    return workspace


def _article(workspace, user, persona=None, trashed=False):
    return Content(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=f"Article {uuid4().hex[:6]}",
        slug=uuid4().hex[:10],
        status="draft",
        persona_id=persona.id if persona else None,
        deleted_at=datetime.now(timezone.utc) if trashed else None,
    )


async def _personas(session, user_id, workspace, monkeypatch):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user_id)}
    # The permission itself is the RBAC tests' concern; here only the count matters.
    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", AsyncMock(return_value=True))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/workspaces/{workspace}/personas")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return {p["name"]: p["article_count"] for p in response.json()["data"]["personas"]}


@pytest.mark.asyncio
async def test_each_persona_counts_its_own_articles_outside_the_trash(session, monkeypatch):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = await _workspace(session, user, "counts")
    other = await _workspace(session, user, "other")
    writer = Persona(workspace_id=workspace.id, name="Writer")
    quiet = Persona(workspace_id=workspace.id, name="Quiet")
    elsewhere = Persona(workspace_id=other.id, name="Elsewhere")
    session.add_all([writer, quiet, elsewhere])
    await session.flush()
    session.add_all(
        [
            _article(workspace, user, writer),
            _article(workspace, user, writer),
            _article(workspace, user, writer, trashed=True),
            _article(workspace, user),
            _article(other, user, elsewhere),
        ]
    )
    await session.flush()

    counts = await _personas(session, user.id, workspace.id, monkeypatch)

    assert counts == {"Writer": 2, "Quiet": 0}


@pytest.mark.asyncio
async def test_a_slug_counts_the_same_as_the_uuid(session, monkeypatch):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = await _workspace(session, user, "slugged")
    writer = Persona(workspace_id=workspace.id, name="Writer")
    session.add(writer)
    await session.flush()
    session.add(_article(workspace, user, writer))
    await session.flush()

    assert await _personas(session, user.id, workspace.slug, monkeypatch) == {"Writer": 1}
