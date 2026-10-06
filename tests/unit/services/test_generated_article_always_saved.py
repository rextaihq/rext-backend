"""A generated article is always saved, whatever its title (G55, revnix/rext-control#498).

The title step offers the same titles for a keyword, so two articles on one keyword can share a
title. A title stays unique only among the live articles written by hand; a generated article (it
carries its generation thread) is saved beside any other with its title, under a slug of its own,
and never overwrites a hand-written article. A save that still fails ends the run as a failure
instead of a success that left nothing in the library.

Checked on the test PostgreSQL: the tables are created inside a transaction that is rolled back,
so the unique index on hand-written titles is the model's.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.api.database.async_database as database_module
import src.flow.engines.content.generation.persist_content as persist_module
import src.services.content_service as service_module
import src.services.notification_helper as notification_module
import src.utils.loop_bridge as loop_module
from src.api.database.base import Base
from src.api.middleware.exceptions import DuplicateResourceException
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.services.content_service import ContentService
from tests.conftest import TEST_DATABASE_URL

TITLE = "Understanding content marketing roi for small business"


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
                sync, tables=_with_their_references([Content, ContentSEOData]), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def owner(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="Titles", slug=f"titles-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    return SimpleNamespace(user=user, workspace=workspace)


@pytest.fixture(autouse=True)
def no_side_services(monkeypatch):
    """The embedding (the LangGraph store) and the activity feed aren't this test's concern."""
    monkeypatch.setattr(
        service_module.ContentEmbeddingService,
        "upsert_content_embedding",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(service_module, "record_content_activity", AsyncMock())


def _article(owner, title=TITLE, thread=None, trashed=False, slug=None, body="An earlier body."):
    return Content(
        workspace_id=owner.workspace.id,
        created_by_user_id=owner.user.id,
        title=title,
        slug=slug or uuid4().hex[:10],
        body_markdown=body,
        status="draft",
        langgraph_thread_id=thread,
        deleted_at=datetime.now(timezone.utc) if trashed else None,
    )


def _generated(title=TITLE, thread=None, body="The new article."):
    return ContentCreate(title=title, body_markdown=body, langgraph_thread_id=thread or uuid4())


async def _rows(session, owner, title=TITLE):
    return (
        (
            await session.execute(
                select(Content).where(
                    Content.workspace_id == owner.workspace.id, Content.title == title
                )
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.asyncio
async def test_a_generated_article_repeating_a_title_is_saved(session, owner):
    earlier = _article(owner, thread=uuid4(), slug="understanding-content-marketing")
    session.add(earlier)
    await session.flush()

    saved = await ContentService(session).create_content(
        owner.workspace.id, owner.user.id, _generated()
    )

    assert saved.id != earlier.id
    assert saved.body_markdown == "The new article."
    assert earlier.body_markdown == "An earlier body."
    assert len(await _rows(session, owner)) == 2


@pytest.mark.asyncio
async def test_a_third_article_with_the_title_is_saved_too(session, owner):
    session.add_all([_article(owner, thread=uuid4()), _article(owner, thread=uuid4())])
    await session.flush()

    await ContentService(session).create_content(owner.workspace.id, owner.user.id, _generated())

    assert len(await _rows(session, owner)) == 3


@pytest.mark.asyncio
async def test_a_generated_article_never_overwrites_a_hand_written_one(session, owner):
    by_hand = _article(owner, body="Written by hand.")
    session.add(by_hand)
    await session.flush()

    saved = await ContentService(session).create_content(
        owner.workspace.id, owner.user.id, _generated()
    )

    assert saved.id != by_hand.id
    assert by_hand.body_markdown == "Written by hand."
    assert by_hand.langgraph_thread_id is None


@pytest.mark.asyncio
async def test_the_same_thread_saves_into_its_own_row(session, owner):
    thread = uuid4()
    mine = _article(owner, thread=thread)
    session.add(mine)
    await session.flush()

    saved = await ContentService(session).create_content(
        owner.workspace.id, owner.user.id, _generated(thread=thread, body="Rewritten.")
    )

    assert saved.id == mine.id
    assert saved.body_markdown == "Rewritten."
    assert len(await _rows(session, owner)) == 1


@pytest.mark.asyncio
async def test_a_hand_written_article_still_needs_a_new_title(session, owner):
    session.add(_article(owner))
    await session.flush()

    with pytest.raises(DuplicateResourceException):
        await ContentService(session).create_content(
            owner.workspace.id, owner.user.id, ContentCreate(title=TITLE)
        )


@pytest.mark.asyncio
async def test_the_database_keeps_hand_written_titles_unique(session, owner):
    session.add(_article(owner))
    await session.flush()

    session.add(_article(owner))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.asyncio
async def test_a_trashed_articles_title_and_slug_are_free_for_a_new_one(session, owner):
    session.add(
        _article(owner, trashed=True, slug="understanding-content-marketing-roi-for-small-business")
    )
    await session.flush()

    saved = await ContentService(session).create_content(
        owner.workspace.id, owner.user.id, ContentCreate(title=TITLE)
    )

    assert saved.slug == "understanding-content-marketing-roi-for-small-business-1"


@pytest.mark.asyncio
async def test_a_generated_article_may_be_renamed_to_a_title_in_use(session, owner):
    session.add(_article(owner, thread=uuid4()))
    renamed = _article(owner, title="Another title", thread=uuid4())
    session.add(renamed)
    await session.flush()

    updated = await ContentService(session).update_content(
        renamed.id, owner.workspace.id, owner.user.id, ContentUpdate(title=TITLE)
    )

    assert updated.title == TITLE
    assert len(await _rows(session, owner)) == 2


@pytest.mark.asyncio
async def test_a_hand_written_article_may_not_be_renamed_to_a_title_in_use(session, owner):
    session.add(_article(owner))
    by_hand = _article(owner, title="Another title")
    session.add(by_hand)
    await session.flush()

    with pytest.raises(DuplicateResourceException):
        await ContentService(session).update_content(
            by_hand.id, owner.workspace.id, owner.user.id, ContentUpdate(title=TITLE)
        )


def _finished_run_state():
    return {
        "content": {
            "selected_topic": TITLE,
            "final_content": {"title": TITLE, "body_markdown": "## Why\n\nBecause."},
        },
        "serp_payload": {"user_id": str(uuid4()), "workspace_id": str(uuid4())},
    }


@pytest.mark.asyncio
async def test_a_save_that_fails_ends_the_run_as_a_failure(monkeypatch):
    class FailingService:
        def __init__(self, db):
            pass

        async def create_content(self, workspace_id, user_id, payload):
            raise RuntimeError("the database went away")

    @asynccontextmanager
    async def fake_db():
        yield None

    notify = AsyncMock()
    monkeypatch.setattr(service_module, "ContentService", FailingService)
    monkeypatch.setattr(database_module, "get_pooled_langgraph_db_context", fake_db)
    monkeypatch.setattr(loop_module, "run_on_main_loop", lambda coro: coro)
    monkeypatch.setattr(notification_module, "notify_now", notify)

    with pytest.raises(persist_module.ArticleNotSaved) as raised:
        await persist_module.persist_content(
            _finished_run_state(), {"configurable": {"thread_id": str(uuid.uuid4())}}
        )

    # What a person may see says what happened, not the exception behind it.
    assert str(raised.value) == "The article couldn't be saved to your library."
    assert isinstance(raised.value.__cause__, RuntimeError)
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_saved_article_is_announced(monkeypatch):
    class SavingService:
        def __init__(self, db):
            pass

        async def create_content(self, workspace_id, user_id, payload):
            return SimpleNamespace(id=uuid.uuid4())

    @asynccontextmanager
    async def fake_db():
        yield None

    notify = AsyncMock()
    monkeypatch.setattr(service_module, "ContentService", SavingService)
    monkeypatch.setattr(database_module, "get_pooled_langgraph_db_context", fake_db)
    monkeypatch.setattr(loop_module, "run_on_main_loop", lambda coro: coro)
    monkeypatch.setattr(notification_module, "notify_now", notify)

    await persist_module.persist_content(
        _finished_run_state(), {"configurable": {"thread_id": str(uuid.uuid4())}}
    )

    notify.assert_awaited_once()
    assert notify.await_args.kwargs["pref_flag"] == "gen_completed"
