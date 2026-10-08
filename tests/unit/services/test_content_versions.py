"""An article's versions: when one is made, what the history lists, what a restore puts back
(FB2.25, rext-control #706).

Checked on the test PostgreSQL: the tables the services read are created inside a transaction
that is rolled back. The embedding and the activity feed, which a save also writes, are replaced.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import DuplicateResourceException, ResourceNotFoundException
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.content_version import ContentVersion, ContentVersionSource
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.services import content_service
from src.services.content_service import ContentService
from src.services.content_version_service import (
    KEPT,
    SITTING,
    ContentVersionService,
    count_words,
    record_published,
    text_of,
    went_live,
)
from tests.conftest import TEST_DATABASE_URL

READ_TABLES = [WorkspaceModel, Content, ContentSEOData, ContentVersion]
EDIT, GENERATION, RESTORE, PUBLISH = (
    ContentVersionSource.EDIT,
    ContentVersionSource.GENERATION,
    ContentVersionSource.RESTORE,
    ContentVersionSource.PUBLISH,
)


def _with_their_references(models):
    """The services' tables and every table their foreign keys point at."""
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
                sync, tables=_with_their_references(READ_TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _user(session, name="Sam Rivera"):
    user = Users(email=f"{uuid4().hex[:12]}@example.com", full_name=name)
    session.add(user)
    await session.flush()
    return user


async def _workspace(session, user):
    workspace = WorkspaceModel(user_id=user.id, name="Versions", slug=f"versions-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    return workspace


async def _article(session, user, workspace, *, generated=True, title=None, **text):
    article = Content(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=title or f"How to Repot a Houseplant {uuid4().hex[:6]}",
        slug=uuid4().hex[:10],
        status="draft",
        introduction=text.get("introduction", "Repotting takes ten minutes."),
        body_markdown=text.get("body_markdown", "## Why repot\n\nRoots need room."),
        body_html=text.get("body_html"),
        images_data=text.get("images_data"),
        langgraph_thread_id=uuid4() if generated else None,
    )
    session.add(article)
    await session.flush()
    return article


async def _setup(session, **article):
    user = await _user(session)
    workspace = await _workspace(session, user)
    return user, workspace, await _article(session, user, workspace, **article)


async def _save(session, article, user, **changes):
    return await ContentService(session).update_content(
        article.id, article.workspace_id, user.id, ContentUpdate(**changes), version_as=EDIT
    )


async def _versions(session, article):
    return await ContentVersionService(session).list(article.id, article.workspace_id)


async def _age(session, article, by: timedelta):
    """Move the article's versions back in time, as if the sitting had begun earlier."""
    await session.execute(
        update(ContentVersion)
        .where(ContentVersion.content_id == article.id)
        .values(created_at=ContentVersion.created_at - by)
    )
    for loaded in list(session.identity_map.values()):
        if isinstance(loaded, ContentVersion):
            session.expire(loaded)


@pytest.mark.asyncio
async def test_the_first_save_keeps_the_article_as_generated_and_then_the_edit(session):
    user, workspace, article = await _setup(session)
    was = text_of(article)

    await _save(session, article, user, body_markdown="## Why repot\n\nRoots need room. And air.")

    newest, first = await _versions(session, article)
    assert (first["source"], newest["source"]) == ("generation", "edit")
    assert first["title"] == was["title"]
    assert first["word_count"] == count_words(was["introduction"], was["body_markdown"])
    assert first["created_by"] == {"id": user.id, "name": "Sam Rivera"}
    assert newest["word_count"] == first["word_count"] + 2
    assert first["created_at"] <= newest["created_at"]
    kept, _ = await ContentVersionService(session).get(article.id, first["id"], workspace.id)
    assert text_of(kept) == was


@pytest.mark.asyncio
async def test_an_article_written_by_hand_has_an_edit_as_its_first_version(session):
    user, _, article = await _setup(session, generated=False)

    await _save(session, article, user, introduction="A new opening.")

    assert [v["source"] for v in await _versions(session, article)] == ["edit", "edit"]


@pytest.mark.asyncio
async def test_the_saves_of_one_sitting_are_one_version(session):
    user, _, article = await _setup(session)

    for text in ("One.", "One. Two.", "One. Two. Three."):
        await _save(session, article, user, body_markdown=text)

    newest, first = await _versions(session, article)
    assert first["source"] == "generation"
    assert newest["word_count"] == count_words(article.introduction, "One. Two. Three.")
    # Amended by the sitting's later saves; the first version never was.
    assert newest["updated_at"] > newest["created_at"]
    assert first["updated_at"] is None


@pytest.mark.asyncio
async def test_a_new_version_after_the_sitting_and_for_another_person(session):
    user, workspace, article = await _setup(session)
    other = await _user(session, "Ada Park")

    await _save(session, article, user, body_markdown="One.")
    await _age(session, article, SITTING + timedelta(seconds=1))
    await _save(session, article, user, body_markdown="One. Two.")
    await _save(session, article, other, body_markdown="One. Two. Three.")

    versions = await _versions(session, article)
    assert [v["source"] for v in versions] == ["edit", "edit", "edit", "generation"]
    assert versions[0]["created_by"] == {"id": other.id, "name": "Ada Park"}
    assert versions[1]["created_by"]["id"] == user.id


@pytest.mark.asyncio
async def test_a_save_that_leaves_the_text_as_it_was_makes_no_version(session):
    user, _, article = await _setup(session)

    # The same text again, and a save of something that is no text of the article.
    await _save(session, article, user, body_markdown=article.body_markdown)
    await _save(session, article, user, tags=["plants"], category="Home")

    assert await _versions(session, article) == []


@pytest.mark.asyncio
async def test_a_save_without_a_person_behind_it_makes_no_version(session):
    user, workspace, article = await _setup(session)

    # The generation run saving its article again: no `version_as`.
    await ContentService(session).update_content(
        article.id, workspace.id, user.id, ContentUpdate(body_markdown="Written again by the run.")
    )

    assert await _versions(session, article) == []


@pytest.mark.asyncio
async def test_the_newest_are_kept(session):
    user, _, article = await _setup(session)

    for number in range(KEPT + 4):
        await _save(session, article, user, body_markdown=f"Text number {number}.")
        await _age(session, article, SITTING + timedelta(seconds=1))

    versions = await _versions(session, article)
    assert len(versions) == KEPT
    stored = await session.scalar(
        select(func.count())
        .select_from(ContentVersion)
        .where(ContentVersion.content_id == article.id)
    )
    assert stored == KEPT
    # The oldest went: the article as generated among them.
    assert "generation" not in {v["source"] for v in versions}
    newest, _ = await ContentVersionService(session).get(
        article.id, versions[0]["id"], article.workspace_id
    )
    assert newest.body_markdown == f"Text number {KEPT + 3}."


@pytest.mark.asyncio
async def test_a_restore_keeps_what_was_there_and_puts_the_whole_version_back(session):
    user, workspace, article = await _setup(
        session, body_html="<p>Roots need room.</p>", images_data={"hero": "a.png"}
    )
    generated = text_of(article)
    await _save(
        session,
        article,
        user,
        title="A New Title for the Repotting Guide",
        introduction="Changed.",
        body_markdown="Changed body.",
        body_html="<p>Changed body.</p>",
        images_data={"hero": "b.png"},
    )
    edited = text_of(article)
    first = (await _versions(session, article))[-1]

    restored = await ContentService(session).restore_version(
        article.id, first["id"], workspace.id, user.id
    )

    assert text_of(restored) == generated
    versions = await _versions(session, article)
    assert [v["source"] for v in versions] == ["restore", "edit", "generation"]
    # The edit is still there to go back to.
    kept, _ = await ContentVersionService(session).get(article.id, versions[1]["id"], workspace.id)
    assert text_of(kept) == edited


@pytest.mark.asyncio
async def test_a_restore_empties_what_the_version_has_empty(session):
    user, workspace, article = await _setup(session, introduction=None, body_html=None)
    await _save(session, article, user, introduction="Added later.", body_html="<p>Added.</p>")
    first = (await _versions(session, article))[-1]

    restored = await ContentService(session).restore_version(
        article.id, first["id"], workspace.id, user.id
    )

    assert restored.introduction is None
    assert restored.body_html is None


@pytest.mark.asyncio
async def test_a_restore_after_an_unsaved_sitting_keeps_the_text_as_it_stood(session):
    user, workspace, article = await _setup(session)
    await _save(session, article, user, body_markdown="First edit.")
    first = (await _versions(session, article))[-1]
    # The run wrote the article again since (no version of that), then the customer restores.
    await ContentService(session).update_content(
        article.id, workspace.id, user.id, ContentUpdate(body_markdown="Written by the run.")
    )

    await ContentService(session).restore_version(article.id, first["id"], workspace.id, user.id)

    versions = await _versions(session, article)
    assert [v["source"] for v in versions] == ["restore", "edit", "edit", "generation"]
    before_restore, _ = await ContentVersionService(session).get(
        article.id, versions[1]["id"], workspace.id
    )
    assert before_restore.body_markdown == "Written by the run."


@pytest.mark.asyncio
async def test_a_restored_title_follows_the_rule_of_any_rename(session):
    user, workspace, article = await _setup(session, generated=False, title="Repotting by Hand")
    await _save(session, article, user, title="Repotting, Second Title")
    first = (await _versions(session, article))[-1]
    # Another article written by hand took the first title meanwhile.
    await _article(session, user, workspace, generated=False, title="Repotting by Hand")

    with pytest.raises(DuplicateResourceException):
        await ContentService(session).restore_version(
            article.id, first["id"], workspace.id, user.id
        )


@pytest.mark.asyncio
async def test_a_version_of_another_article_or_workspace_is_not_found(session):
    user, workspace, article = await _setup(session)
    await _save(session, article, user, body_markdown="Edited.")
    version_id = (await _versions(session, article))[0]["id"]
    other_article = await _article(session, user, workspace)
    other_user = await _user(session, "Ada Park")
    other_workspace = await _workspace(session, other_user)
    versions, service = ContentVersionService(session), ContentService(session)

    with pytest.raises(ResourceNotFoundException):
        await versions.get(other_article.id, version_id, workspace.id)
    with pytest.raises(ResourceNotFoundException):
        await versions.get(article.id, version_id, other_workspace.id)
    with pytest.raises(ResourceNotFoundException):
        await versions.get(article.id, uuid4(), workspace.id)
    with pytest.raises(ResourceNotFoundException):
        await service.restore_version(other_article.id, version_id, workspace.id, user.id)
    with pytest.raises(ResourceNotFoundException):
        await service.restore_version(article.id, version_id, other_workspace.id, other_user.id)
    assert await versions.list(article.id, other_workspace.id) == []


@pytest.mark.asyncio
async def test_a_publish_is_a_version_of_its_own_once(session):
    user, _, article = await _setup(session)
    versions = ContentVersionService(session)

    await versions.record(article, text_of(article), user.id, PUBLISH)
    await versions.record(article, text_of(article), user.id, PUBLISH)

    assert [v["source"] for v in await _versions(session, article)] == ["publish"]

    # After an edit, the next publish marks the text as it then went out.
    await _save(session, article, user, body_markdown="Edited after publishing.")
    await versions.record(article, text_of(article), user.id, PUBLISH)
    assert [v["source"] for v in await _versions(session, article)] == [
        "publish",
        "edit",
        "publish",
    ]


@pytest.mark.asyncio
async def test_a_scheduled_publish_keeps_the_text_as_it_went_out_with_no_maker(session):
    user, _, article = await _setup(session)
    await _save(session, article, user, body_markdown="Edited before the schedule ran.")

    # The scheduler has published it: no request, so nobody is the version's maker.
    await record_published(session, article)
    await record_published(session, article)  # the same text again: one version

    newest, *older = await _versions(session, article)
    assert (newest["source"], newest["created_by"]) == ("publish", None)
    assert [v["source"] for v in older] == ["edit", "generation"]


@pytest.mark.asyncio
async def test_a_scheduled_publish_keeps_what_was_sent_not_what_the_article_became(session):
    user, _, article = await _setup(session)
    sent = text_of(article)

    # Edited while the post was on its way to the site.
    await _save(session, article, user, body_markdown="Edited while it was being published.")
    await record_published(session, article, text=sent)
    await record_published(session, article, text=sent)  # once

    versions = ContentVersionService(session)
    newest, *older = await _versions(session, article)
    assert newest["source"] == "publish"
    assert (await versions.get(article.id, newest["id"], article.workspace_id))[
        0
    ].body_markdown == sent["body_markdown"]
    assert [v["source"] for v in older] == ["edit", "generation"]


@pytest.mark.asyncio
async def test_a_persons_save_of_a_generated_article_is_an_edit_and_the_runs_own_is_not(session):
    """The save endpoints reach an article its run already stored through create_content: a
    person's save is kept as an edit, with the text it replaced; the run saving again is not."""
    user, workspace, article = await _setup(session)
    service = ContentService(session)

    def saved_again(body):
        return ContentCreate(
            title=article.title,
            introduction=article.introduction,
            body_markdown=body,
            langgraph_thread_id=article.langgraph_thread_id,
        )

    await service.create_content(workspace.id, user.id, saved_again("Written again by the run."))
    assert await _versions(session, article) == []

    await service.create_content(
        workspace.id, user.id, saved_again("Edited before saving."), version_as=EDIT
    )
    assert [v["source"] for v in await _versions(session, article)] == ["edit", "generation"]


@pytest.mark.asyncio
async def test_an_untitled_articles_first_version_keeps_its_empty_title(session):
    user, workspace, article = await _setup(session, generated=False)
    article.title = ""
    await session.flush()

    await _save(session, article, user, title="A Title At Last")

    newest, first = await _versions(session, article)
    assert (first["title"], newest["title"]) == ("", "A Title At Last")


def _site(success=True, shopify=None, wordpress=None):
    return type(
        "Result",
        (),
        {"success": success, "shopify_article_id": shopify, "wordpress_post_id": wordpress},
    )()


@pytest.mark.parametrize(
    ("status", "results", "live"),
    [
        ("published", [_site(wordpress=7)], True),
        ("published", [_site(success=False)], False),
        # WordPress waits for its date, Shopify took the article now.
        ("scheduled", [_site(shopify=3), _site(wordpress=None)], True),
        ("scheduled", [_site(wordpress=None)], False),
        ("draft", [_site(wordpress=7)], False),
        ("scheduled", [_site(success=False, shopify=3)], False),
    ],
)
def test_a_publish_is_a_version_when_a_site_took_the_text_now(status, results, live):
    assert went_live(status, results) is live


@pytest.mark.asyncio
async def test_a_version_that_cannot_be_kept_does_not_stop_the_publish(session, monkeypatch):
    user, _, article = await _setup(session)
    article.status = "published"
    monkeypatch.setattr(
        ContentVersionService, "record", AsyncMock(side_effect=RuntimeError("no room"))
    )

    await record_published(session, article)

    # The caller's own work is still there to be saved.
    await session.flush()
    assert (await session.get(Content, article.id)).status == "published"
    assert await _versions(session, article) == []


@pytest.mark.asyncio
async def test_versions_go_with_their_article_and_outlive_their_maker(session):
    user, workspace, article = await _setup(session)
    editor = await _user(session, "Ada Park")
    await _save(session, article, editor, body_markdown="Edited by Ada.")
    article_id, workspace_id = article.id, workspace.id
    versions = ContentVersionService(session)

    await session.execute(delete(Users).where(Users.id == editor.id))
    session.expire_all()
    newest = (await versions.list(article_id, workspace_id))[0]
    assert newest["created_by"] is None
    assert newest["source"] == "edit"

    await session.execute(delete(Content).where(Content.id == article_id))
    session.expire_all()
    left = await session.scalar(
        select(func.count())
        .select_from(ContentVersion)
        .where(ContentVersion.content_id == article_id)
    )
    assert left == 0


def test_the_words_of_a_version_are_those_of_its_introduction_and_body():
    assert count_words("Two words.", "## A heading\n\nThree more words.") == 8
    assert count_words(None, None) == 0
    assert datetime.now(timezone.utc) - SITTING < datetime.now(timezone.utc)
