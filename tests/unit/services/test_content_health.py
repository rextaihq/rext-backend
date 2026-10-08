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
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.content_service import ContentService, _host_of
from tests.conftest import TEST_DATABASE_URL

READ_TABLES = [
    WorkspaceModel,
    Content,
    ContentSEOData,
    ContentPublishingResult,
    WorkspaceIntegration,
]


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
    wordpress=False,
    shopify=False,
):
    """An article; `meta` left out means no SEO row at all. `wordpress` and `shopify`: published
    there (True), or the state its publishing result is left in ("deleted"): the article keeps
    the site's id either way, as a publish leaves it."""
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
        wordpress_post_id=1 if wordpress else None,
        shopify_article_id=1 if shopify else None,
    )
    session.add(article)
    await session.flush()
    if meta is not ...:
        session.add(ContentSEOData(content_id=article.id, meta_description=meta))
        await session.flush()
    for native_id, state in (("wp_post_id", wordpress), ("shopify_article_id", shopify)):
        if not state:
            continue
        site = WorkspaceIntegration(workspace_id=workspace.id, is_active=True)
        session.add(site)
        await session.flush()
        session.add(
            ContentPublishingResult(
                content_id=article.id,
                site_id=site.id,
                status="published" if state is True else state,
                **{native_id: 1},
            )
        )
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
    # An image and a link: the link counts.
    await _article(
        session, user, workspace, body="![Hero](/images/hero.jpg) Then [pricing](/pricing)."
    )
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
    # An image on the site is no link to it, in Markdown or in HTML.
    await _article(session, user, workspace, body="![Hero](/images/hero.jpg) and text.")
    await _article(session, user, workspace, body="![Hero](https://example.com/hero.jpg)")
    await _article(
        session, user, workspace, body=None, html='<p><img src="https://example.com/a.png"></p>'
    )
    # Markdown is what gets published: an older HTML copy with a link doesn't count.
    await _article(session, user, workspace, body="No link.", html='<a href="/pricing">Pricing</a>')
    await _article(session, user, workspace, body="No link at all.")
    await _article(session, user, workspace, body=None)

    health = await ContentService(session).content_health(workspace.id)

    assert health["published"] == 21
    assert health["no_internal_links"] == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("article", "links"),
    [
        # Relative to the article's own address: no host, so the same site (rext-control #791).
        ({"body": "See [pricing](pricing)."}, True),
        ({"body": "Our [plans](../plans/) page."}, True),
        ({"body": "Read [this part](./guide.html#part)."}, True),
        ({"body": "A [page](Guide.HTML?from=article) of ours."}, True),
        ({"body": "The [setup notes](docs/setup.md)."}, True),
        ({"body": "The [guide](guide.en.html) in English."}, True),
        ({"body": None, "html": '<a href="release.v2.html">The release</a>'}, True),
        ({"body": None, "html": '<a href="pricing">Pricing</a>'}, True),
        ({"body": None, "html": "<a href='plans/pro'>Pro</a>"}, True),
        # An attribute without quotes, relative or from the root.
        ({"body": None, "html": "<a href=pricing>Pricing</a>"}, True),
        ({"body": None, "html": "<a href=/pricing>Pricing</a>"}, True),
        # A scheme, a place on the same page, nothing at all: no link to another page of the site.
        ({"body": "Write to [us](mailto:hi@example.com)."}, False),
        ({"body": "Call [us](tel:+15551234)."}, False),
        ({"body": "Back to [the top](#top)."}, False),
        ({"body": "The [next page](?page=2)."}, False),
        ({"body": "An [empty link]()."}, False),
        (
            {"body": None, "html": '<a href="javascript:void(0)">Open</a> <a href="#">Top</a>'},
            False,
        ),
        # Another site's address written without its scheme, and an email address.
        ({"body": "From [another site](www.other.com/page)."}, False),
        ({"body": "From [another site](other.com/x), or [this one](other.com)."}, False),
        ({"body": "Write to [them](hi@other.com)."}, False),
        ({"body": "Write to [support](support+blog@other.com)."}, False),
        ({"body": "Write to [her](first_last@other.com)."}, False),
        # Round brackets that open no link, and an image beside the article.
        ({"body": "Plain text (pricing) and [square] (pricing)."}, False),
        ({"body": "![Hero](hero.jpg) and text."}, False),
    ],
)
async def test_a_link_relative_to_the_article_is_a_link_to_the_site(session, article, links):
    user, workspace = await _workspace(session, url="https://example.com")
    await _article(session, user, workspace, **article)

    health = await ContentService(session).content_health(workspace.id)

    assert health["no_internal_links"] == (0 if links else 1)


@pytest.mark.asyncio
async def test_an_article_is_read_as_its_site_was_sent_it(session):
    user, workspace = await _workspace(session, url="https://example.com")
    linked, plain = '<a href="/pricing">Pricing</a>', "<p>No link.</p>"
    # Shopify is sent the HTML body when there is one, and the Markdown one when there is none.
    await _article(session, user, workspace, body="No link.", html=linked, shopify=True)
    await _article(session, user, workspace, body="See [pricing](/pricing).", shopify=True)
    await _article(
        session, user, workspace, body="See [pricing](/pricing).", html=plain, shopify=True
    )
    # On both sites each was sent its own body: a link in either counts.
    both = {"shopify": True, "wordpress": True}
    await _article(session, user, workspace, body="No link.", html=linked, **both)
    await _article(session, user, workspace, body="See [pricing](/pricing).", html=plain, **both)
    await _article(session, user, workspace, body="No link.", html=plain, **both)
    # On WordPress alone, as with no site recorded: Markdown first.
    await _article(session, user, workspace, body="No link.", html=linked, wordpress=True)
    # A post deleted on its site is live there no more, though the article keeps its id: with
    # the Shopify one gone, the HTML body's link is on no site.
    gone = {"shopify": "deleted", "wordpress": True}
    await _article(session, user, workspace, body="No link.", html=linked, **gone)
    await _article(session, user, workspace, body="No link.", html=linked, shopify="deleted")
    # And with the WordPress one gone, Shopify's HTML body is the article.
    await _article(
        session, user, workspace, body="No link.", html=linked, shopify=True, wordpress="trashed"
    )

    health = await ContentService(session).content_health(workspace.id)

    assert health["published"] == 10
    assert health["no_internal_links"] == 5


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
