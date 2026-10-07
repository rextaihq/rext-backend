"""The home's content health counts (FB2.27a, rext-control #765).

Over a workspace's published articles: how many have no meta description, and how many link to
none of the workspace's own sites. Checked on the test PostgreSQL: the tables the service reads
are created inside a transaction that is rolled back.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.content_service import ContentService, _host_of
from tests.conftest import TEST_DATABASE_URL

READ_TABLES = [WorkspaceModel, Content, ContentSEOData, WorkspaceIntegration]


def _with_their_references(models):
    """The service's tables and every table their foreign keys point at."""
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


async def _workspace(session, *, url=None, sites=()):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(
        user_id=user.id, name="Health", slug=f"health-{uuid4().hex[:8]}", url=url
    )
    session.add(workspace)
    await session.flush()
    for site_url, active in sites:
        session.add(
            WorkspaceIntegration(workspace_id=workspace.id, site_url=site_url, is_active=active)
        )
    await session.flush()
    return user, workspace


async def _article(
    session,
    user,
    workspace,
    *,
    status="published",
    body="",
    html=None,
    intro=None,
    meta=...,
    trashed=False,
):
    """An article; `meta` left out means no SEO row at all."""
    article = Content(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=f"{status} {uuid4().hex[:6]}",
        slug=uuid4().hex[:10],
        status=status,
        body_markdown=body,
        introduction=intro,
        body_html=html,
        deleted_at=datetime.now(timezone.utc) if trashed else None,
    )
    session.add(article)
    await session.flush()
    if meta is not ...:
        session.add(ContentSEOData(content_id=article.id, meta_description=meta))
        await session.flush()
    return article


@pytest.mark.asyncio
async def test_nothing_published_counts_nothing(session):
    user, workspace = await _workspace(session, url="https://example.com")
    await _article(session, user, workspace, status="draft")

    assert await ContentService(session).content_health(workspace.id) == {
        "published": 0,
        "missing_meta_description": 0,
        "no_internal_links": 0,
    }


@pytest.mark.asyncio
async def test_a_missing_or_blank_meta_description_is_counted(session):
    user, workspace = await _workspace(session)
    await _article(session, user, workspace, meta="A real description of the article.")
    await _article(session, user, workspace, meta=None)
    await _article(session, user, workspace, meta="   ")
    await _article(session, user, workspace, meta="\n\t \r\n")
    await _article(session, user, workspace)  # no SEO row at all
    # Not published, or in the trash: not counted.
    await _article(session, user, workspace, status="draft", meta=None)
    await _article(session, user, workspace, meta=None, trashed=True)

    health = await ContentService(session).content_health(workspace.id)

    assert health["published"] == 5
    assert health["missing_meta_description"] == 4


@pytest.mark.asyncio
async def test_an_article_linking_to_none_of_the_workspaces_sites_is_counted(session):
    user, workspace = await _workspace(
        session,
        url="https://www.example.com/",
        sites=[("https://blog.example.org", True), ("https://old.example.net", False)],
    )
    await _article(session, user, workspace, body="See [pricing](https://example.com/pricing).")
    await _article(session, user, workspace, body="Read [this](http://www.example.com/a) too.")
    await _article(session, user, workspace, body="On [the blog](https://blog.example.org/p).")
    await _article(session, user, workspace, body="Ends on a bare address: https://example.com")
    # From the site's root, and without a scheme: links to the site all the same.
    await _article(session, user, workspace, body="See [pricing](/pricing) for the plans.")
    await _article(session, user, workspace, body="A [guide](//example.com/guide) to read.")
    # No Markdown body: the HTML one is what gets published.
    await _article(session, user, workspace, body=None, html='<a href="/pricing">Pricing</a>')
    await _article(
        session, user, workspace, body="", html='<a href="https://example.com/a">Read on</a>'
    )
    # The article is its introduction and its body: a link in either counts.
    await _article(
        session, user, workspace, intro="From [our guide](https://example.com/guide).", body="Text."
    )
    # A site that is no longer connected, another site, a host that only starts the same.
    await _article(session, user, workspace, body="An [old link](https://old.example.net/p).")
    await _article(session, user, workspace, body="A [source](https://other.com/example.com).")
    await _article(session, user, workspace, body="A [lookalike](https://example.com.au/article).")
    await _article(session, user, workspace, body="A [shop](https://shop.example.com/item).")
    await _article(session, user, workspace, body="Elsewhere: [x](//other.com/x), and/or 1/2.")
    # Markdown is what gets published: an older HTML copy with a link doesn't count.
    await _article(session, user, workspace, body="No link.", html='<a href="/pricing">Pricing</a>')
    await _article(session, user, workspace, body="No link at all.")
    await _article(session, user, workspace, body=None)

    health = await ContentService(session).content_health(workspace.id)

    assert health["published"] == 17
    assert health["no_internal_links"] == 8


@pytest.mark.asyncio
async def test_without_an_address_the_link_count_is_unknown(session):
    user, workspace = await _workspace(session, sites=[(None, True)])
    await _article(session, user, workspace, body="A [link](https://example.com).")

    health = await ContentService(session).content_health(workspace.id)

    assert health["published"] == 1
    assert health["no_internal_links"] is None


@pytest.mark.asyncio
async def test_another_workspaces_articles_and_sites_are_not_counted(session):
    user, workspace = await _workspace(session, url="https://example.com")
    other_user, other = await _workspace(session, url="https://other.com")
    await _article(session, user, workspace, body="A [link](https://other.com/x).", meta="Yes.")
    await _article(session, other_user, other, body="Nothing.", meta=None)

    health = await ContentService(session).content_health(workspace.id)

    assert health == {"published": 1, "missing_meta_description": 0, "no_internal_links": 1}


@pytest.mark.parametrize(
    ("address", "host"),
    [
        ("https://www.Example.com/blog/", "example.com"),
        ("example.com", "example.com"),
        ("http://shop.example.com:8080", "shop.example.com"),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_the_host_of_an_address(address, host):
    assert _host_of(address) == host
