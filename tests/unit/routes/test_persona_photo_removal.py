"""Removing or replacing a persona's uploaded photo (G64) answers 200, and the stored file it
no longer shows is deleted once the change is committed. Before, the clean-up's listener removed
itself while SQLAlchemy was dispatching the commit, which failed the request with a 500 after the
change had been saved.

Checked on the test PostgreSQL: the tables the route reads are created inside a transaction
that is rolled back. Storage is stubbed.
"""

import io
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

# UserRole: the route's workspace lookup asks whether the caller is a super admin.
TABLES = [WorkspaceModel, WorkspaceMembers, Persona, UserRole]


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


@pytest.fixture
def storage(monkeypatch):
    """The object store: uploads succeed and deletions are recorded; nothing leaves the test."""
    from src.utils.storage import storage_service

    deleted = Mock()
    monkeypatch.setattr(storage_service, "delete_file", deleted)
    monkeypatch.setattr(storage_service, "upload_file", Mock(return_value=True))
    return deleted


async def _persona_with_uploaded_photo(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="Photos", slug=f"photos-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    persona = Persona(workspace_id=workspace.id, name="Marketing Mary")
    session.add(persona)
    await session.flush()
    persona.avatar_url = f"avatars/personas/{persona.id}/avatar_1.png"
    persona.avatar_source = "custom"
    await session.flush()
    return user, workspace, persona


async def _call(session, user, monkeypatch, method, path, **kwargs):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    # The permission itself is the RBAC tests' concern; here only the save matters.
    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", AsyncMock(return_value=True))
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _put(session, user, workspace, persona, body, monkeypatch):
    return await _call(
        session,
        user,
        monkeypatch,
        "PUT",
        f"/api/v1/workspaces/{workspace.id}/personas/{persona.id}",
        json=body,
    )


def _png() -> bytes:
    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 120, 90)).save(out, format="PNG")
    return out.getvalue()


@pytest.mark.asyncio
async def test_removing_an_uploaded_photo_answers_200_and_deletes_the_file(
    session, storage, monkeypatch
):
    user, workspace, persona = await _persona_with_uploaded_photo(session)
    stored = persona.avatar_url

    response = await _put(
        session, user, workspace, persona, {"name": "Marketing Mary", "avatar_url": ""}, monkeypatch
    )

    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert saved["avatar_source"] == "generated"
    assert saved["avatar_url"].startswith("data:image/svg+xml")
    storage.assert_called_once_with(stored)


@pytest.mark.asyncio
async def test_an_edit_that_keeps_the_photo_deletes_nothing(session, storage, monkeypatch):
    user, workspace, persona = await _persona_with_uploaded_photo(session)

    response = await _put(
        session, user, workspace, persona, {"name": "Marketing Maria"}, monkeypatch
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["avatar_source"] == "custom"
    storage.assert_not_called()


@pytest.mark.asyncio
async def test_uploading_a_new_photo_answers_200_and_deletes_the_old_file(
    session, storage, monkeypatch
):
    user, workspace, persona = await _persona_with_uploaded_photo(session)
    stored = persona.avatar_url

    response = await _call(
        session,
        user,
        monkeypatch,
        "POST",
        f"/api/v1/workspaces/{workspace.id}/personas/{persona.id}/avatar",
        files={"file": ("new.png", _png(), "image/png")},
    )

    assert response.status_code == 200, response.text
    await session.refresh(persona)
    assert persona.avatar_url != stored
    assert persona.avatar_url.startswith(f"avatars/personas/{persona.id}/")
    storage.assert_called_once_with(stored)
