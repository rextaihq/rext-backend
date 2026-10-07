"""GET /api/v1/content/health: the route, its permission and its response (FB2.27a, #765).

The counts themselves are tested on the service (tests/unit/services/test_content_health.py).
Checked on the test PostgreSQL inside a rolled-back transaction, with the role lookup replaced.
"""

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
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

TABLES = [WorkspaceModel, WorkspaceMembers, Content, ContentSEOData, WorkspaceIntegration, UserRole]


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
                sync, tables=_with_their_references(TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


def _permission(monkeypatch, allowed: bool):
    # Imported inside require_permissions' wrapper, so patched where they are defined.
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_all_permissions", AsyncMock(return_value=allowed)
    )
    monkeypatch.setattr(
        "src.utils.rbac_utils.check_any_permission", AsyncMock(return_value=allowed)
    )


async def _health(session, user, workspace):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.get("/api/v1/content/health", params={"workspace_id": str(workspace)})
    finally:
        app.dependency_overrides.clear()


async def _workspace_with_articles(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(
        user_id=user.id,
        name="Health",
        slug=f"health-{uuid4().hex[:8]}",
        url="https://example.com",
    )
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    for body in ("See [pricing](https://example.com/pricing).", "No link."):
        session.add(
            Content(
                workspace_id=workspace.id,
                created_by_user_id=user.id,
                title=f"Article {uuid4().hex[:6]}",
                slug=uuid4().hex[:10],
                status="published",
                body_markdown=body,
            )
        )
    await session.flush()
    return user, workspace


@pytest.mark.asyncio
async def test_a_member_reads_the_workspaces_counts_by_id_or_slug(session, monkeypatch):
    _permission(monkeypatch, True)
    user, workspace = await _workspace_with_articles(session)

    for identifier in (workspace.id, workspace.slug):
        response = await _health(session, user, identifier)

        assert response.status_code == 200, response.text
        assert response.json()["data"] == {
            "published": 2,
            "missing_meta_description": 2,
            "no_internal_links": 1,
        }


@pytest.mark.asyncio
async def test_without_the_permission_it_is_refused(session, monkeypatch):
    _permission(monkeypatch, False)
    user, workspace = await _workspace_with_articles(session)

    response = await _health(session, user, workspace.id)

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_someone_outside_the_workspace_reads_nothing(session, monkeypatch):
    _permission(monkeypatch, True)
    _, workspace = await _workspace_with_articles(session)
    outsider = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(outsider)
    await session.flush()

    response = await _health(session, outsider, workspace.id)

    assert response.status_code in (403, 404), response.text
    assert "published" not in response.text
