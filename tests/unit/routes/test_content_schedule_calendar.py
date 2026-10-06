"""Moving a scheduled publish to another day, and the calendar's days.

PATCH /api/v1/content/{id}/schedule moves every site the content is scheduled on
to the new day at its own time of day, in the account's timezone, and changes
nothing else (D9, revnix/rext-control#240). GET /api/v1/content/calendar groups
the month by the same timezone. Checked on the test PostgreSQL inside a
rolled-back transaction, with the permission check and the CMS sync replaced.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.models.content_models.content import Content
from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.utils.datetime_utils import account_zone, moved_to_day
from tests.conftest import TEST_DATABASE_URL

TABLES = [
    WorkspaceModel,
    WorkspaceMembers,
    Content,
    ContentPublishingResult,
    WorkspaceIntegration,
    # Loading the caller for their timezone reads their roles.
    UserRole,
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
                sync, tables=_with_their_references(TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture(autouse=True)
def allowed(monkeypatch):
    # Imported inside require_permissions' wrapper, so patched where they are defined.
    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", AsyncMock(return_value=True))
    monkeypatch.setattr("src.utils.rbac_utils.check_any_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.api.routes.content.modules.calendar.CMSStatusService.bulk_sync_workspace",
        AsyncMock(return_value=None),
    )


async def _call(session, user, method, path, **kwargs):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(method, f"/api/v1/content{path}", **kwargs)
    finally:
        app.dependency_overrides.clear()


async def _workspace(session, tz="UTC"):
    user = Users(email=f"{uuid4().hex[:12]}@example.com", timezone=tz)
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(user_id=user.id, name="Calendar", slug=f"cal-{uuid4().hex[:8]}")
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    sites = [
        WorkspaceIntegration(
            workspace_id=workspace.id,
            integration_type="wordpress",
            is_active=True,
            site_url=f"https://{name}.example.com",
        )
        for name in ("one", "two", "three")
    ]
    session.add_all(sites)
    await session.flush()
    return user, workspace, sites


async def _content(session, user, workspace, status, published_at):
    content = Content(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title=f"{status} {uuid4().hex[:6]}",
        slug=uuid4().hex[:10],
        status=status,
        wordpress_published_at=published_at,
    )
    session.add(content)
    await session.flush()
    return content


def _record(content, site, status, at=None):
    return ContentPublishingResult(
        content_id=content.id, site_id=site.id, status=status, scheduled_publish_at=at
    )


def _days_ahead(days, hour, minute=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )


def test_a_moved_publish_keeps_its_local_time_across_a_clock_change():
    # 09:00 in New York on 30 October 2026 (EDT, UTC-4) is 13:00 UTC; on
    # 2 November the clocks have gone back (EST, UTC-5), so 09:00 is 14:00 UTC.
    when = datetime(2026, 10, 30, 13, 0, tzinfo=timezone.utc)

    moved = moved_to_day(when, date(2026, 11, 2), "America/New_York")

    assert moved == datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


def test_an_unknown_account_timezone_reads_as_utc():
    assert account_zone("Not/A_Zone") is timezone.utc
    assert account_zone(None) is not None


@pytest.mark.asyncio
async def test_moving_a_schedule_moves_every_scheduled_site_and_nothing_else(session):
    user, workspace, (one, two, three) = await _workspace(session)
    at_nine = _days_ahead(3, 9)
    content = await _content(session, user, workspace, "scheduled", at_nine)
    title = content.title
    first = _record(content, one, PublishingStatus.SCHEDULED, at_nine)
    second = _record(content, two, PublishingStatus.SCHEDULED, at_nine.replace(hour=15, minute=30))
    published = _record(content, three, PublishingStatus.PUBLISHED)
    session.add_all([first, second, published])
    await session.flush()
    new_day = (at_nine + timedelta(days=4)).date()

    response = await _call(
        session,
        user,
        "PATCH",
        f"/{content.id}/schedule?workspace_id={workspace.id}",
        json={"day": new_day.isoformat()},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["rescheduled_records"] == 2
    rows = {
        r.site_id: r
        for r in (
            await session.execute(
                select(ContentPublishingResult).where(
                    ContentPublishingResult.content_id == content.id
                )
            )
        ).scalars()
    }
    # Each site keeps its own time of day on the new day.
    assert rows[one.id].scheduled_publish_at == datetime.combine(new_day, at_nine.timetz()).replace(
        tzinfo=timezone.utc
    )
    assert rows[two.id].scheduled_publish_at.date() == new_day
    assert (rows[two.id].scheduled_publish_at.hour, rows[two.id].scheduled_publish_at.minute) == (
        15,
        30,
    )
    assert rows[two.id].status == PublishingStatus.SCHEDULED
    # The site it was already published on is left as it was.
    assert rows[three.id].status == PublishingStatus.PUBLISHED
    assert rows[three.id].scheduled_publish_at is None
    await session.refresh(content)
    assert content.status == "scheduled"
    assert content.title == title
    assert content.wordpress_published_at.date() == new_day
    assert datetime.fromisoformat(data["scheduled_at"]) == content.wordpress_published_at


@pytest.mark.asyncio
async def test_only_a_scheduled_publish_can_move(session):
    user, workspace, (one, _, _) = await _workspace(session)
    content = await _content(session, user, workspace, "published", _days_ahead(-1, 9))

    response = await _call(
        session,
        user,
        "PATCH",
        f"/{content.id}/schedule?workspace_id={workspace.id}",
        json={"day": _days_ahead(5, 9).date().isoformat()},
    )

    assert response.status_code == 400, response.text
    assert "not scheduled" in response.text


@pytest.mark.asyncio
async def test_a_day_in_the_past_is_refused(session):
    user, workspace, (one, _, _) = await _workspace(session)
    at_nine = _days_ahead(3, 9)
    content = await _content(session, user, workspace, "scheduled", at_nine)
    record = _record(content, one, PublishingStatus.SCHEDULED, at_nine)
    session.add(record)
    await session.flush()

    response = await _call(
        session,
        user,
        "PATCH",
        f"/{content.id}/schedule?workspace_id={workspace.id}",
        json={"day": _days_ahead(-2, 9).date().isoformat()},
    )

    # Refused before anything is written; the request's rollback undoes the rest.
    assert response.status_code == 400, response.text
    assert "future" in response.text


@pytest.mark.asyncio
async def test_a_publish_that_is_already_due_cannot_move(session):
    user, workspace, (one, _, _) = await _workspace(session)
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    content = await _content(session, user, workspace, "scheduled", due)
    session.add(_record(content, one, PublishingStatus.SCHEDULED, due))
    await session.flush()

    response = await _call(
        session,
        user,
        "PATCH",
        f"/{content.id}/schedule?workspace_id={workspace.id}",
        json={"day": _days_ahead(5, 9).date().isoformat()},
    )

    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_the_calendar_puts_an_item_on_the_account_timezones_day(session):
    # 21:00 UTC on 31 October 2026 is 02:00 on 1 November in Karachi (UTC+5).
    user, workspace, _ = await _workspace(session, tz="Asia/Karachi")
    late = datetime(2026, 10, 31, 21, 0, tzinfo=timezone.utc)
    content = await _content(session, user, workspace, "scheduled", late)

    november = await _call(
        session, user, "GET", f"/calendar?workspace_id={workspace.id}&year=2026&month=11"
    )
    october = await _call(
        session, user, "GET", f"/calendar?workspace_id={workspace.id}&year=2026&month=10"
    )

    assert november.status_code == 200, november.text
    data = november.json()["data"]
    assert data["timezone"] == "Asia/Karachi"
    assert [e["id"] for e in data["calendar"]["2026-11-01"]] == [str(content.id)]
    assert october.json()["data"]["calendar"] == {}
