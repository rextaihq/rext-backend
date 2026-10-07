"""PATCH /api/v1/user/profile announces a profile edit, not the dashboard's own timezone save (D17).

The dashboard writes the browser's timezone to the profile by itself, so a save of the timezone
alone sent "Your profile has been successfully updated." to someone who had edited nothing.
Checked on the test PostgreSQL: the user's tables are created inside a transaction that is rolled back.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL
from tests.db_tables import create_tables_unless_migrated


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            # UserRole: the user's lookup loads their roles.
            lambda sync: create_tables_unless_migrated(sync, [Users, UserRole])
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


async def _save(session, monkeypatch, body):
    from src.api.server import app

    user = Users(email=f"{uuid4().hex[:12]}@example.com", timezone="UTC")
    session.add(user)
    await session.flush()
    notice = AsyncMock()
    monkeypatch.setattr("src.api.routes.users.profile.schedule_if_allowed", notice)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.patch("/api/v1/user/profile", json=body)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    return response.json()["data"], notice


@pytest.mark.asyncio
async def test_the_dashboards_timezone_save_is_not_announced(session, monkeypatch):
    data, notice = await _save(session, monkeypatch, {"timezone": "Asia/Karachi"})

    assert data["updated_fields"] == ["timezone"]
    assert data["profile"]["timezone"] == "Asia/Karachi"
    notice.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_profile_edit_is_announced(session, monkeypatch):
    data, notice = await _save(session, monkeypatch, {"full_name": "Mary Jane"})

    assert data["updated_fields"] == ["full_name"]
    notice.assert_awaited_once()
    assert notice.await_args.kwargs["payload"]["updated_fields"] == ["full_name"]


@pytest.mark.asyncio
async def test_an_edit_saved_with_the_timezone_is_announced(session, monkeypatch):
    _, notice = await _save(
        session, monkeypatch, {"full_name": "Mary Jane", "timezone": "Asia/Karachi"}
    )

    notice.assert_awaited_once()
    assert notice.await_args.kwargs["payload"]["updated_fields"] == ["full_name", "timezone"]
