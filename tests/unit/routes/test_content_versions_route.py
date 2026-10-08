"""The editor's history over HTTP: the three version routes, their permission and their answers
(FB2.25, rext-control #706).

When a version is made and what a restore does are tested on the services
(tests/unit/services/test_content_versions.py). Checked on the test PostgreSQL inside a rolled-back
transaction, with the role lookup, the embedding and the activity feed replaced.
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
from src.api.models.content_models.content_version import ContentVersion
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.services import content_service
from tests.conftest import TEST_DATABASE_URL

TABLES = [WorkspaceModel, WorkspaceMembers, Content, ContentSEOData, ContentVersion, UserRole]


def _with_their_references(models):
    """The routes' tables and every table their foreign keys point at."""
    tables, stack = set(), [model.__table__ for model in models]
    while stack:
        table = stack.pop()
        if table not in tables:
            tables.add(table)
            stack.extend(fk.column.table for fk in table.foreign_keys)
    return list(tables)


@pytest_asyncio.fixture
async def session(monkeypatch):
    # A save also writes the article's embedding and the activity feed: neither is under test.
    monkeypatch.setattr(
        content_service.ContentEmbeddingService, "upsert_content_embedding", AsyncMock()
    )
    monkeypatch.setattr(content_service, "record_content_activity", AsyncMock())
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=_with_their_references(TABLES), checkfirst=True
            )
        )
        # A refused request rolls its session back: to the session's savepoint, or the rollback
        # would take the test's own transaction, and the tables made in it, with it.
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as db:
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


async def _call(session, user, method, path, workspace, **kwargs):
    from src.api.server import app

    async def override_get_db():
        yield session

    # The caller as a user or as a user's id: read now, not when the request arrives.
    identity = str(getattr(user, "id", user))
    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": identity}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(
                method,
                f"/api/v1/content/{path}",
                params={"workspace_id": str(workspace)},
                **kwargs,
            )
    finally:
        app.dependency_overrides.clear()


async def _workspace_with_an_article(session, name="Sam Rivera"):
    user = Users(email=f"{uuid4().hex[:12]}@example.com", full_name=name)
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="Versions", slug=f"versions-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    article = Content(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=f"How to Repot a Houseplant {uuid4().hex[:6]}",
        slug=uuid4().hex[:10],
        status="draft",
        introduction="Repotting takes ten minutes.",
        body_markdown="## Why repot\n\nRoots need room.",
        langgraph_thread_id=uuid4(),
    )
    session.add(article)
    await session.flush()
    return user, workspace, article


@pytest.mark.asyncio
async def test_an_edit_is_listed_shown_and_put_back(session, monkeypatch):
    _permission(monkeypatch, True)
    user, workspace, article = await _workspace_with_an_article(session)
    generated = article.body_markdown

    # Nothing before the first save through the editor.
    listed = await _call(session, user, "GET", f"{article.id}/versions", workspace.id)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == {"versions": []}

    saved = await _call(
        session,
        user,
        "PATCH",
        str(article.id),
        workspace.id,
        json={"body_markdown": "## Why repot\n\nRoots need room. And air."},
    )
    assert saved.status_code == 200, saved.text

    # By the workspace's slug too, as every content route reads it.
    listed = await _call(session, user, "GET", f"{article.id}/versions", workspace.slug)
    versions = listed.json()["data"]["versions"]
    assert [version["source"] for version in versions] == ["edit", "generation"]
    newest, first = versions
    assert set(newest) == {
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "source",
        "title",
        "word_count",
    }
    assert newest["created_by"] == {"id": str(user.id), "name": "Sam Rivera"}
    assert newest["title"] == article.title
    assert newest["word_count"] == first["word_count"] + 2

    shown = await _call(session, user, "GET", f"{article.id}/versions/{first['id']}", workspace.id)
    assert shown.status_code == 200, shown.text
    detail = shown.json()["data"]
    assert detail["body_markdown"] == generated
    assert detail["introduction"] == "Repotting takes ten minutes."
    # What a restore puts back besides: there to be shown, empty for this article.
    assert {"body_html", "images_data"} <= set(detail)
    assert detail["source"] == "generation"

    restored = await _call(
        session, user, "POST", f"{article.id}/versions/{first['id']}/restore", workspace.id
    )
    assert restored.status_code == 200, restored.text
    # The answer is the article, as a save of it answers.
    assert restored.json()["data"]["id"] == str(article.id)
    assert restored.json()["data"]["body_markdown"] == generated

    listed = await _call(session, user, "GET", f"{article.id}/versions", workspace.id)
    assert [version["source"] for version in listed.json()["data"]["versions"]] == [
        "restore",
        "edit",
        "generation",
    ]


@pytest.mark.asyncio
async def test_a_restore_takes_the_editors_unsaved_text_with_it(session, monkeypatch):
    _permission(monkeypatch, True)
    user, workspace, article = await _workspace_with_an_article(session)
    generated = article.body_markdown
    await _call(
        session, user, "PATCH", str(article.id), workspace.id, json={"body_markdown": "Saved."}
    )
    listed = await _call(session, user, "GET", f"{article.id}/versions", workspace.id)
    first = listed.json()["data"]["versions"][-1]["id"]

    restored = await _call(
        session,
        user,
        "POST",
        f"{article.id}/versions/{first}/restore",
        workspace.id,
        json={"body_markdown": "Typed and never saved."},
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["data"]["body_markdown"] == generated
    listed = await _call(session, user, "GET", f"{article.id}/versions", workspace.id)
    versions = listed.json()["data"]["versions"]
    assert [version["source"] for version in versions] == ["restore", "edit", "edit", "generation"]
    typed = await _call(
        session, user, "GET", f"{article.id}/versions/{versions[1]['id']}", workspace.id
    )
    assert typed.json()["data"]["body_markdown"] == "Typed and never saved."

    # A field the text does not have is refused before anything is restored.
    refused = await _call(
        session,
        user,
        "POST",
        f"{article.id}/versions/{first}/restore",
        workspace.id,
        json={"status": "published"},
    )
    assert refused.status_code == 422, refused.text


@pytest.mark.asyncio
async def test_without_the_permission_to_edit_each_route_is_refused(session, monkeypatch):
    user, workspace, article = await _workspace_with_an_article(session)
    _permission(monkeypatch, True)
    await _call(
        session, user, "PATCH", str(article.id), workspace.id, json={"body_markdown": "Edited."}
    )
    version = (await _call(session, user, "GET", f"{article.id}/versions", workspace.id)).json()[
        "data"
    ]["versions"][0]["id"]

    _permission(monkeypatch, False)
    for method, path in (
        ("GET", f"{article.id}/versions"),
        ("GET", f"{article.id}/versions/{version}"),
        ("POST", f"{article.id}/versions/{version}/restore"),
    ):
        response = await _call(session, user, method, path, workspace.id)
        assert response.status_code == 403, (method, path, response.text)


@pytest.mark.asyncio
async def test_a_version_of_another_article_or_workspace_is_not_found(session, monkeypatch):
    _permission(monkeypatch, True)
    user, workspace, article = await _workspace_with_an_article(session)
    other_user, other_workspace, other_article = await _workspace_with_an_article(
        session, "Ada Park"
    )
    # Plain values: a refused request rolls the session back, and its rows then need reading again.
    here, there = workspace.id, other_workspace.id
    mine, theirs = article.id, other_article.id
    user, other_user = user.id, other_user.id
    await _call(session, user, "PATCH", str(mine), here, json={"body_markdown": "Edited."})
    version = (await _call(session, user, "GET", f"{mine}/versions", here)).json()["data"][
        "versions"
    ][0]["id"]

    # This article's version asked for under another article, an id that is no version, and an
    # article that isn't there.
    response = await _call(session, other_user, "GET", f"{theirs}/versions/{version}", there)
    assert response.status_code == 404, response.text
    response = await _call(session, user, "GET", f"{mine}/versions/{uuid4()}", here)
    assert response.status_code == 404, response.text
    response = await _call(session, user, "GET", f"{uuid4()}/versions", here)
    assert response.status_code == 404, response.text

    # Another workspace's member, in their own workspace, reaches neither the article nor it.
    for method, path in (
        ("GET", f"{mine}/versions"),
        ("GET", f"{mine}/versions/{version}"),
        ("POST", f"{mine}/versions/{version}/restore"),
    ):
        response = await _call(session, other_user, method, path, there)
        assert response.status_code == 404, (method, path, response.text)

    # And in the article's workspace they are no member at all.
    response = await _call(session, other_user, "GET", f"{mine}/versions", here)
    assert response.status_code in (403, 404), response.text
    # Nothing was restored along the way.
    kept = await _call(session, user, "GET", f"{mine}/versions", here)
    assert [v["source"] for v in kept.json()["data"]["versions"]] == ["edit", "generation"]


@pytest.mark.asyncio
async def test_an_id_that_is_no_id_is_refused_before_anything_is_read(session, monkeypatch):
    _permission(monkeypatch, True)
    user, workspace, article = await _workspace_with_an_article(session)

    response = await _call(session, user, "GET", f"{article.id}/versions/latest", workspace.id)

    assert response.status_code == 422, response.text
