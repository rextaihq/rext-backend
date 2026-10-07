"""GET /api/v1/dashboard/{workspace} counts the library as the library lists it.

Trashed content is in neither the draft, published nor total count, and a slug in
the path gives the same counts as the UUID. Checked on the test PostgreSQL: the
tables the route reads are created inside a transaction that is rolled back.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

READ_TABLES = [
    WorkspaceModel,
    WorkspaceMembers,
    Content,
    Persona,
    AuditLog,
]


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


async def _dashboard(session, user_id, workspace):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user_id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(f"/api/v1/dashboard/{workspace}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _workspace_with_content(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="Counts", slug=f"counts-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))

    def item(status, trashed=False):
        return Content(
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            title=f"{status} {uuid4().hex[:6]}",
            slug=uuid4().hex[:10],
            status=status,
            deleted_at=datetime.now(timezone.utc) if trashed else None,
        )

    session.add_all(
        [
            item("draft"),
            item("draft"),
            item("draft", trashed=True),
            item("published"),
            item("published", trashed=True),
            Persona(workspace_id=workspace.id, name="Editor"),
        ]
    )
    await session.flush()
    return user, workspace


@pytest.mark.asyncio
async def test_the_trash_is_left_out_of_every_content_count(session):
    user, workspace = await _workspace_with_content(session)

    data = await _dashboard(session, user.id, workspace.id)

    assert data["content"] == {"total": 3, "published": 1, "draft": 2}
    assert data["personas"] == 1


@pytest.mark.asyncio
async def test_a_slug_counts_the_same_as_the_uuid(session):
    user, workspace = await _workspace_with_content(session)

    by_id = await _dashboard(session, user.id, workspace.id)
    by_slug = await _dashboard(session, user.id, workspace.slug)

    assert by_slug["content"] == by_id["content"] == {"total": 3, "published": 1, "draft": 2}
    # The response names the workspace by its UUID, as WorkspaceDashboardResponse declares.
    assert by_slug["workspace_id"] == by_id["workspace_id"] == str(workspace.id)
    assert by_slug["personas"] == by_id["personas"] == 1
