"""A workspace's trash (G45, rext-control #397): deleted articles and personas are listed,
restored as they were, deleted for good, and purged after the retention window.

Checked on the test PostgreSQL: the tables are created inside a transaction that is rolled back,
and each session works in a savepoint of it, so nothing is left behind. The store (embeddings)
and the file storage are stubbed; nothing reaches the network.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.workspace_trash_service as trash_module
from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.error_handler import setup_exception_handlers
from src.api.middleware.exceptions import DuplicateResourceException, ResourceNotFoundException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.services.content_activity import ACTION_RESTORED
from src.services.persona_names import reject_duplicate_persona_name
from src.services.workspace_trash_service import ARTICLE, PERSONA, WorkspaceTrashService
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)
TABLES = [Users, WorkspaceModel, Persona, Content, ContentSEOData, AuditLog]


@pytest_asyncio.fixture
async def connection():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[t.__table__ for t in TABLES], checkfirst=True
            )
        )
        yield conn
        await transaction.rollback()
    await engine.dispose()


def _session(conn):
    # A commit inside the code under test stops at the session's savepoint.
    return AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")


@pytest_asyncio.fixture
async def db(connection):
    async with _session(connection) as session:
        yield session


@pytest.fixture
def forgotten(monkeypatch):
    """The embeddings removed from the store, by (workspace, content id)."""
    calls = []

    async def forget(workspace_id, content_id):
        calls.append((workspace_id, content_id))
        return True

    from src.services.content_embedding_service import ContentEmbeddingService

    monkeypatch.setattr(ContentEmbeddingService, "delete_content_embedding", staticmethod(forget))
    return calls


@pytest.fixture
def removed_files(monkeypatch):
    """The stored files the purge removes."""
    names = []

    async def remove(object_names):
        names.extend(object_names)

    monkeypatch.setattr(trash_module, "remove_stored_files", remove)
    return names


async def _user(db, name="Ann Writer"):
    user = Users(email=f"{uuid4().hex[:12]}@example.com", full_name=name)
    db.add(user)
    await db.flush()
    return user


async def _workspace(db, owner):
    workspace = WorkspaceModel(user_id=owner.id, name="Bakery", slug=f"bakery-{uuid4().hex[:8]}")
    db.add(workspace)
    await db.flush()
    return workspace


async def _article(
    db, workspace, author, *, title=None, deleted_days_ago=None, by=None, thread=None
):
    title = title or f"Sourdough {uuid4().hex[:6]}"
    article = Content(
        workspace_id=workspace.id,
        created_by_user_id=author.id,
        title=title,
        slug=f"sourdough-{uuid4().hex[:8]}",
        body_markdown="Flour, water, salt.",
        status="draft",
        langgraph_thread_id=thread,
        deleted_at=NOW - timedelta(days=deleted_days_ago) if deleted_days_ago is not None else None,
        deleted_by=by.id if by else None,
    )
    db.add(article)
    await db.flush()
    return article


async def _persona(db, workspace, *, name=None, deleted_days_ago=None, by=None, avatar_url=None):
    persona = Persona(
        workspace_id=workspace.id,
        name=name or f"Baker {uuid4().hex[:6]}",
        bio="Twenty years at the oven.",
        avatar_url=avatar_url,
        deleted_at=NOW - timedelta(days=deleted_days_ago) if deleted_days_ago is not None else None,
        deleted_by=by.id if by else None,
    )
    db.add(persona)
    await db.flush()
    return persona


# --- the list --------------------------------------------------------------------------------


async def test_the_trash_lists_deleted_articles_and_personas_newest_first_with_who_and_when(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    other = await _workspace(db, ann)
    await _article(db, workspace, ann)  # live: not in the trash
    article = await _article(db, workspace, ann, deleted_days_ago=2, by=ann)
    persona = await _persona(db, workspace, deleted_days_ago=1, by=ann)
    await _article(db, other, ann, deleted_days_ago=1, by=ann)  # another workspace's

    items, total = await WorkspaceTrashService(db).list_trash(workspace.id, now=NOW)

    assert total == 2
    assert [(i["kind"], i["id"]) for i in items] == [
        (PERSONA, str(persona.id)),
        (ARTICLE, str(article.id)),
    ]
    assert items[0]["name"] == persona.name
    assert items[1]["name"] == article.title
    assert items[1]["deleted_by"] == {"id": str(ann.id), "name": "Ann Writer"}
    assert items[1]["days_remaining"] == 28
    assert items[0]["days_remaining"] == 29


async def test_the_list_shows_only_the_kinds_the_caller_may_read(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    await _article(db, workspace, ann, deleted_days_ago=1)
    await _persona(db, workspace, deleted_days_ago=1)

    articles, total = await WorkspaceTrashService(db).list_trash(workspace.id, kinds=[ARTICLE])
    nothing, none = await WorkspaceTrashService(db).list_trash(workspace.id, kinds=[])

    assert total == 1 and [i["kind"] for i in articles] == [ARTICLE]
    assert (nothing, none) == ([], 0)


async def test_the_list_pages(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    for days in (1, 2, 3):
        await _article(db, workspace, ann, deleted_days_ago=days)

    page, total = await WorkspaceTrashService(db).list_trash(workspace.id, limit=2, offset=2)

    assert total == 3 and len(page) == 1 and page[0]["days_remaining"] == 26


async def test_an_item_past_the_window_is_neither_listed_nor_restorable(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    old = await _article(db, workspace, ann, deleted_days_ago=31)

    items, total = await WorkspaceTrashService(db).list_trash(workspace.id, now=NOW)
    assert (items, total) == ([], 0)
    with pytest.raises(ResourceNotFoundException):
        await WorkspaceTrashService(db).restore(workspace.id, ARTICLE, old.id, user_id=ann.id)


# --- restore ---------------------------------------------------------------------------------


async def test_restoring_brings_an_article_back_as_it_was(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    article = await _article(db, workspace, ann, deleted_days_ago=3, by=ann)

    await WorkspaceTrashService(db).restore(workspace.id, ARTICLE, article.id, user_id=ann.id)

    back = (await db.execute(select(Content).where(Content.id == article.id))).scalar_one()
    assert back.deleted_at is None and back.deleted_by is None
    assert (back.title, back.body_markdown, back.status) == (
        article.title,
        "Flour, water, salt.",
        "draft",
    )
    logged = (
        await db.execute(select(AuditLog).where(AuditLog.resource_id == str(article.id)))
    ).scalar_one()
    assert logged.action == ACTION_RESTORED


async def test_a_hand_written_article_is_not_restored_while_a_live_one_has_its_title(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    trashed = await _article(db, workspace, ann, title="Rye at home", deleted_days_ago=1)
    await _article(db, workspace, ann, title="Rye at home")  # written since

    with pytest.raises(DuplicateResourceException, match="Rye at home"):
        await WorkspaceTrashService(db).restore(workspace.id, ARTICLE, trashed.id, user_id=ann.id)


async def test_a_generated_article_comes_back_whatever_its_title(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    trashed = await _article(db, workspace, ann, title="Rye", deleted_days_ago=1, thread=uuid4())
    await _article(db, workspace, ann, title="Rye")

    await WorkspaceTrashService(db).restore(workspace.id, ARTICLE, trashed.id, user_id=ann.id)

    assert trashed.deleted_at is None


async def test_restoring_a_persona_brings_it_back_unless_a_live_one_has_its_name(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    persona = await _persona(db, workspace, name="Mary Jane", deleted_days_ago=1, by=ann)
    taken = await _persona(db, workspace, name="Bob")
    second = await _persona(db, workspace, name=" bob ", deleted_days_ago=1)

    await WorkspaceTrashService(db).restore(workspace.id, PERSONA, persona.id, user_id=ann.id)
    assert persona.deleted_at is None and persona.bio == "Twenty years at the oven."

    with pytest.raises(DuplicateResourceException, match="bob"):
        await WorkspaceTrashService(db).restore(workspace.id, PERSONA, second.id, user_id=ann.id)
    assert taken.deleted_at is None


async def test_a_name_in_the_trash_can_be_taken_by_a_new_persona(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    await _persona(db, workspace, name="Mary Jane", deleted_days_ago=1)

    await reject_duplicate_persona_name(db, workspace.id, "mary jane")  # no refusal


async def test_another_workspaces_items_and_live_items_are_out_of_reach(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    other = await _workspace(db, ann)
    theirs = await _article(db, other, ann, deleted_days_ago=1)
    live = await _persona(db, workspace)
    service = WorkspaceTrashService(db)

    for kind, item in ((ARTICLE, theirs), (PERSONA, live)):
        with pytest.raises(ResourceNotFoundException):
            await service.restore(workspace.id, kind, item.id, user_id=ann.id)
        with pytest.raises(ResourceNotFoundException):
            await service.delete_forever(workspace.id, kind, item.id)
    assert theirs.deleted_at is not None and live.deleted_at is None


# --- deleting for good -----------------------------------------------------------------------


async def test_deleting_an_article_for_good_takes_its_seo_data_and_its_embedding(db, forgotten):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    article = await _article(db, workspace, ann, deleted_days_ago=1)
    db.add(ContentSEOData(content_id=article.id, focus_keyphrase="sourdough"))
    await db.flush()

    cleanup = await WorkspaceTrashService(db).delete_forever(workspace.id, ARTICLE, article.id)

    assert cleanup.files == [] and cleanup.embeddings == [(workspace.id, article.id)]
    assert forgotten == []  # not before the commit: the caller runs it after
    assert await db.scalar(select(Content.id).where(Content.id == article.id)) is None
    assert (
        await db.scalar(
            select(ContentSEOData.content_id).where(ContentSEOData.content_id == article.id)
        )
        is None
    )
    await cleanup.run()
    assert forgotten == [(workspace.id, article.id)]


async def test_deleting_a_persona_for_good_leaves_its_articles_without_a_byline(db):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    persona = await _persona(
        db, workspace, deleted_days_ago=1, avatar_url="avatars/personas/abc.webp"
    )
    article = await _article(db, workspace, ann)
    article.persona_id = persona.id
    await db.flush()

    cleanup = await WorkspaceTrashService(db).delete_forever(workspace.id, PERSONA, persona.id)

    assert cleanup.files == ["avatars/personas/abc.webp"]  # removed once committed
    assert cleanup.embeddings == []
    assert await db.scalar(select(Persona.id).where(Persona.id == persona.id)) is None
    assert (await db.scalar(select(Content.persona_id).where(Content.id == article.id))) is None
    assert await db.scalar(select(Content.id).where(Content.id == article.id)) == article.id


# --- the purge -------------------------------------------------------------------------------


async def test_the_purge_deletes_what_is_past_the_window_and_keeps_the_rest(
    db, forgotten, removed_files
):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    old_article = await _article(db, workspace, ann, deleted_days_ago=31)
    recent_article = await _article(db, workspace, ann, deleted_days_ago=29)
    live_article = await _article(db, workspace, ann)
    old_persona = await _persona(
        db, workspace, deleted_days_ago=40, avatar_url="avatars/personas/old.webp"
    )
    linked_persona = await _persona(
        db, workspace, deleted_days_ago=35, avatar_url="https://example.com/me.jpg"
    )
    recent_persona = await _persona(db, workspace, deleted_days_ago=2)

    purged = await WorkspaceTrashService(db).purge_expired(now=NOW, batch_size=1)

    assert purged == {ARTICLE: 1, PERSONA: 2}
    left = set((await db.execute(select(Content.id))).scalars()) | set(
        (await db.execute(select(Persona.id))).scalars()
    )
    assert {recent_article.id, live_article.id, recent_persona.id} <= left
    assert not {old_article.id, old_persona.id, linked_persona.id} & left
    assert forgotten == [(workspace.id, old_article.id)]
    assert removed_files == ["avatars/personas/old.webp"]  # a linked picture isn't ours


async def test_the_purge_cleans_up_only_what_it_deleted(db, removed_files, monkeypatch):
    """A persona restored between the purge's read and its delete stays, with its photo."""
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    restored = await _persona(
        db, workspace, deleted_days_ago=40, avatar_url="avatars/personas/restored.webp"
    )
    await _persona(db, workspace, deleted_days_ago=40, avatar_url="avatars/personas/gone.webp")
    execute = db.execute

    async def restore_first(statement, *args, **kwargs):
        if getattr(statement, "is_delete", False) and restored.deleted_at is not None:
            await execute(update(Persona).where(Persona.id == restored.id).values(deleted_at=None))
            restored.deleted_at = None
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", restore_first)
    purged = await WorkspaceTrashService(db).purge_expired(now=NOW)

    assert purged == {ARTICLE: 0, PERSONA: 1}
    assert removed_files == ["avatars/personas/gone.webp"]
    assert await execute(select(Persona.id).where(Persona.id == restored.id))


async def test_the_window_is_a_setting(db, monkeypatch):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    await _article(db, workspace, ann, deleted_days_ago=8)
    monkeypatch.setattr(trash_module, "retention_days", lambda: 7)

    items, total = await WorkspaceTrashService(db).list_trash(workspace.id, now=NOW)

    assert (items, total) == ([], 0)


# --- the routes ------------------------------------------------------------------------------


@pytest.fixture
def app_for(connection, monkeypatch):
    """The workspace routers on the test database, the caller resolved to a member."""
    import src.api.routes.workspaces.workspace_personas as personas_routes
    import src.api.routes.workspaces.workspace_trash as trash_routes
    import src.utils.rbac_utils as rbac

    def build(user, workspace, *, readable=("content.read", "persona.read")):
        async def resolved(*, db, workspace_identifier, user):
            return workspace, None

        async def may(db, user_id, permission, workspace_id=None):
            return permission in readable

        monkeypatch.setattr(personas_routes, "resolve_workspace_for_route", resolved)
        monkeypatch.setattr(trash_routes, "resolve_workspace_for_route", resolved)
        monkeypatch.setattr(trash_routes, "check_permission", may)
        monkeypatch.setattr(trash_routes, "is_user_super_admin", AsyncMock(return_value=False))
        monkeypatch.setattr(rbac, "is_user_super_admin", AsyncMock(return_value=False))
        monkeypatch.setattr(rbac, "check_any_permission", AsyncMock(return_value=True))
        monkeypatch.setattr(rbac, "check_all_permissions", AsyncMock(return_value=True))

        app = FastAPI()
        setup_exception_handlers(app)  # a refusal answers as it does in the app (404, 409)
        app.include_router(personas_routes.router, prefix="/workspaces")
        app.include_router(trash_routes.router, prefix="/workspaces")

        async def override_db():
            async with _session(connection) as session:
                yield session

        app.dependency_overrides[get_async_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return build


async def test_deleting_a_persona_puts_it_in_the_trash_and_out_of_the_list(db, app_for):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    persona = await _persona(db, workspace, name="Mary Jane")
    await _persona(db, workspace, name="Bob")
    await db.commit()

    async with app_for(ann, workspace) as client:
        deleted = await client.delete(f"/workspaces/{workspace.id}/personas/{persona.id}")
        listed = await client.get(f"/workspaces/{workspace.id}/personas")
        trash = await client.get(f"/workspaces/{workspace.id}/trash")
        restored = await client.post(
            f"/workspaces/{workspace.id}/trash/personas/{persona.id}/restore"
        )
        relisted = await client.get(f"/workspaces/{workspace.id}/personas")

    assert deleted.status_code == 200
    assert [p["name"] for p in listed.json()["data"]["personas"]] == ["Bob"]
    item = trash.json()["data"]["items"][0]
    assert (item["kind"], item["id"], item["deleted_by"]["id"]) == (
        PERSONA,
        str(persona.id),
        str(ann.id),
    )
    assert trash.json()["data"]["retention_days"] == 30
    assert restored.status_code == 200
    assert sorted(p["name"] for p in relisted.json()["data"]["personas"]) == ["Bob", "Mary Jane"]


async def test_the_trash_shows_only_what_the_caller_may_read(db, app_for):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    await _article(db, workspace, ann, deleted_days_ago=1)
    await _persona(db, workspace, deleted_days_ago=1)
    await db.commit()

    async with app_for(ann, workspace, readable=("content.read",)) as client:
        trash = await client.get(f"/workspaces/{workspace.id}/trash")

    assert [i["kind"] for i in trash.json()["data"]["items"]] == [ARTICLE]


async def test_deleting_an_article_for_good_through_the_route(db, app_for, forgotten):
    ann = await _user(db)
    workspace = await _workspace(db, ann)
    article = await _article(db, workspace, ann, deleted_days_ago=1)
    await db.commit()

    async with app_for(ann, workspace) as client:
        gone = await client.delete(f"/workspaces/{workspace.id}/trash/articles/{article.id}")
        again = await client.delete(f"/workspaces/{workspace.id}/trash/articles/{article.id}")

    assert gone.status_code == 200
    assert forgotten == [(workspace.id, article.id)]  # after the commit, as a background task
    assert again.status_code == 404
    assert isinstance(UUID(gone.json()["data"]["id"]), UUID)
