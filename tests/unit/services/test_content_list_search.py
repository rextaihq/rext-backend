"""The content list searches, filters and sorts on the server (rext-control#381).

The library pages there instead of loading every article: ``q`` over the title and the address
of a site an article went out to, lists of statuses and personas (``none`` for no persona), a
sort by any of the library's columns with empty values last and the id breaking ties, and a
``total_count`` for the filtered set. Checked on the test PostgreSQL: the tables are created
inside a transaction that is rolled back.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import RextValidationException
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.content_models.publishing_result import ContentPublishingResult
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.routes.content.modules.content_retrieval import (
    parse_personas,
    parse_sort,
    parse_statuses,
)
from src.services.content_service import ContentService
from tests.conftest import TEST_DATABASE_URL

TABLES = [
    WorkspaceModel,
    WorkspaceMembers,
    Content,
    ContentSEOData,
    ContentPublishingResult,
    WorkspaceIntegration,
    Persona,
]
T0 = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _with_their_references(models):
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


@pytest_asyncio.fixture
async def library(session):
    """One workspace: five articles, two personas, one site, and an article elsewhere."""
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="lib", slug=f"lib-{uuid4().hex[:8]}")
    other = WorkspaceModel(user_id=user.id, name="other", slug=f"other-{uuid4().hex[:8]}")
    session.add_all([workspace, other])
    await session.flush()
    alice = Persona(workspace_id=workspace.id, name="alice")
    bob = Persona(workspace_id=workspace.id, name="Bob")
    site = WorkspaceIntegration(
        workspace_id=workspace.id, integration_type="wordpress", site_url="https://blog.example"
    )
    session.add_all([alice, bob, site])
    await session.flush()

    def article(title, status, minutes, persona=None, **extra):
        return Content(
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            title=title,
            slug=uuid4().hex[:10],
            status=status,
            persona_id=persona.id if persona else None,
            created_at=T0 + timedelta(minutes=minutes),
            updated_at=T0 + timedelta(minutes=minutes),
            **extra,
        )

    arts = {
        "roi": article("Content ROI, 100% explained", "published", 1, alice),
        "seo": article("SEO basics", "draft", 2, bob),
        "cal": article("Calendar template", "review", 3),
        "faq": article("faq_template guide", "draft", 4, alice),
        "old": article("Older post", "published", 5, wordpress_url="https://old.example/p"),
        "gone": article("Trashed one", "draft", 6, deleted_at=T0),
    }
    session.add_all(arts.values())
    session.add(
        Content(
            workspace_id=other.id,
            created_by_user_id=user.id,
            title="SEO elsewhere",
            slug=uuid4().hex[:10],
            status="draft",
        )
    )
    await session.flush()
    session.add_all(
        [
            ContentSEOData(content_id=arts["roi"].id, seo_score=80.0),
            ContentSEOData(content_id=arts["seo"].id, seo_score=55.0),
            ContentPublishingResult(
                content_id=arts["roi"].id,
                site_id=site.id,
                status="published",
                external_url="https://blog.example/roi",
            ),
        ]
    )
    await session.flush()
    return workspace, arts, alice, bob


async def _titles(session, workspace, **kwargs):
    result = await ContentService(session).list_content(workspace_id=workspace.id, **kwargs)
    return [item["title"] for item in result["content"]], result["total_count"]


@pytest.mark.asyncio
async def test_with_no_query_it_lists_the_workspace_newest_first_without_the_trash(
    session, library
):
    workspace, *_ = library
    titles, total = await _titles(session, workspace)

    assert titles == [
        "Older post",
        "faq_template guide",
        "Calendar template",
        "SEO basics",
        "Content ROI, 100% explained",
    ]
    assert total == 5


@pytest.mark.asyncio
async def test_the_search_matches_titles_and_sent_sites_and_takes_its_text_literally(
    session, library
):
    workspace, *_ = library

    assert (await _titles(session, workspace, q="seo")) == (["SEO basics"], 1)
    # The address of a site the article went out to.
    assert (await _titles(session, workspace, q="blog.example"))[0] == [
        "Content ROI, 100% explained"
    ]
    # % and _ match themselves, not any text.
    assert (await _titles(session, workspace, q="100%"))[0] == ["Content ROI, 100% explained"]
    assert (await _titles(session, workspace, q="faq_t"))[0] == ["faq_template guide"]
    # As wildcards, these would match "SEO basics" and "Content ROI, 100% explained".
    assert (await _titles(session, workspace, q="SEO_basics")) == ([], 0)
    assert (await _titles(session, workspace, q="ROI%explained")) == ([], 0)


@pytest.mark.asyncio
async def test_status_and_persona_lists_filter_and_the_total_counts_the_filtered_set(
    session, library
):
    workspace, _, alice, bob = library

    titles, total = await _titles(session, workspace, statuses=["draft", "review"], limit=1)
    assert total == 3 and len(titles) == 1
    assert (await _titles(session, workspace, personas=[str(alice.id)]))[1] == 2
    assert sorted((await _titles(session, workspace, personas=["none"]))[0]) == [
        "Calendar template",
        "Older post",
    ]
    assert (
        await _titles(session, workspace, personas=[str(bob.id), "none"], statuses=["draft"])
    ) == (["SEO basics"], 1)


def _key(title):
    """An article's first word: Content, SEO, Calendar, faq_template, Older."""
    return title.split()[0].rstrip(",")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort", "descending", "groups"),
    [
        ("title", False, [{"Calendar"}, {"Content"}, {"faq_template"}, {"Older"}, {"SEO"}]),
        # The library's order: draft, …, review, …, published.
        ("status", False, [{"SEO", "faq_template"}, {"Calendar"}, {"Content", "Older"}]),
        # alice and Bob by name whatever the case; no persona last, either way.
        ("persona", False, [{"Content", "faq_template"}, {"SEO"}, {"Calendar", "Older"}]),
        ("persona", True, [{"SEO"}, {"Content", "faq_template"}, {"Calendar", "Older"}]),
        ("seo", True, [{"Content"}, {"SEO"}, {"Calendar", "faq_template", "Older"}]),
        ("seo", False, [{"SEO"}, {"Content"}, {"Calendar", "faq_template", "Older"}]),
        # One sent site, or an older article's WordPress address, counts as one site.
        ("published_to", True, [{"Content", "Older"}, {"SEO", "Calendar", "faq_template"}]),
        ("updated_at", False, [{"Content"}, {"SEO"}, {"Calendar"}, {"faq_template"}, {"Older"}]),
    ],
)
async def test_each_column_sorts_with_empty_values_last(session, library, sort, descending, groups):
    workspace, *_ = library
    titles, total = await _titles(session, workspace, sort=sort, descending=descending)

    assert total == 5
    start = 0
    for group in groups:
        assert {_key(t) for t in titles[start : start + len(group)]} == group, (sort, titles)
        start += len(group)


@pytest.mark.asyncio
async def test_pages_across_ties_never_repeat_or_skip_an_article(session, library):
    workspace, *_ = library
    seen = []
    for offset in range(0, 5, 2):
        titles, total = await _titles(
            session, workspace, sort="status", descending=False, limit=2, offset=offset
        )
        seen += titles
    assert total == 5
    assert sorted(seen) == sorted(set(seen)) and len(seen) == 5


def test_the_route_reads_lists_and_refuses_what_the_library_does_not_offer():
    assert parse_statuses("draft, review") == ["draft", "review"]
    assert parse_statuses(None) == []
    persona = str(uuid4())
    assert parse_personas(f"{persona},none") == [persona, "none"]
    assert parse_sort(None) == ("created_at", True)
    assert parse_sort("title.asc") == ("title", False)

    for bad in (
        lambda: parse_statuses("draft,trashed"),
        lambda: parse_personas("not-an-id"),
        lambda: parse_sort("words.desc"),
        lambda: parse_sort("title"),
        lambda: parse_sort("title.sideways"),
    ):
        with pytest.raises(RextValidationException):
            bad()
