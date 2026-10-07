"""
Pytest configuration and shared fixtures for all tests.
"""

import asyncio
import os
from typing import AsyncGenerator, Generator

import openai._base_client
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Prevent MinIO/S3 bucket checks at import time during tests.
os.environ.setdefault("REXT_STORAGE_SKIP_BUCKET_CHECK", "1")

from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.server import app

# Get settings to find the database URL
settings = get_settings()

# Test database URL - priority to POSTGRES_URI_CUSTOM from environment
_base_url = settings.POSTGRES_URI_CUSTOM or "postgresql://localhost/mobeen"

# Ensure it's using the async driver for these tests
if _base_url.startswith("postgresql://"):
    TEST_DATABASE_URL = _base_url.replace("postgresql://", "postgresql+asyncpg://")
else:
    TEST_DATABASE_URL = _base_url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    """
    Create async engine for test database.
    Scope: session (created once for all tests)

    NOTE: Tables are assumed to already exist in the database.
    If testing with a separate test database, uncomment the create_all/drop_all lines.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # Set to True for SQL logging
        poolclass=NullPool,  # Disable connection pooling for tests
    )

    # Uncomment these lines if using a separate test database:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Uncomment these lines if using a separate test database:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def dispose_global_async_engine():
    """Dispose global async_engine connection pool after each test to prevent event loop mismatch."""
    yield
    from src.api.database.async_database import async_engine

    await async_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create async database session for each test.
    Uses transaction rollback for test isolation.
    Scope: function (new session per test)
    """
    # Create session factory
    async_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        # Begin nested transaction
        async with session.begin():
            yield session
            # Rollback happens automatically when context exits
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create async test client with database session override.
    Scope: function (new client per test)
    """

    # Override database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_db

    # Create async client
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

    # Clean up
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def setup_factories(db_session: AsyncSession):
    """
    Set up factories with database session.
    All factories will use this session for creating instances.
    """
    from tests.factories import (
        ContentFactory,
        InvitationFactory,
        PersonaFactory,
        RoleFactory,
        UserFactory,
        WorkspaceFactory,
        WorkspaceMemberFactory,
    )

    # Set session for all factories
    UserFactory._session = db_session
    WorkspaceFactory._session = db_session
    WorkspaceMemberFactory._session = db_session
    ContentFactory._session = db_session
    RoleFactory._session = db_session
    InvitationFactory._session = db_session
    PersonaFactory._session = db_session

    yield {
        "user": UserFactory,
        "workspace": WorkspaceFactory,
        "workspace_member": WorkspaceMemberFactory,
        "content": ContentFactory,
        "role": RoleFactory,
        "invitation": InvitationFactory,
        "persona": PersonaFactory,
    }

    # Cleanup is handled by db_session rollback


@pytest.fixture
def allow_permissions(monkeypatch):
    async def _allow(*args, **kwargs):
        return True

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", _allow)
    monkeypatch.setattr("src.utils.rbac_utils.check_any_permission", _allow)


# --- No real model provider in the tests (G76, rext-control#613) ---------------------------------
# A test that reached OpenAI spent real credits on every check, and when the account ran out on
# 2026-10-07 (G75) unrelated branches failed. Every request the OpenAI client would send is refused
# here, and the test that tried fails, so a new live call is caught where it's written. A test that
# truly needs a live model is marked `live_model`, and runs only with RUN_LIVE_MODEL_TESTS=1.
RUN_LIVE_MODEL_TESTS = os.environ.get("RUN_LIVE_MODEL_TESTS") == "1"


class LiveModelCallBlocked(RuntimeError):
    """A unit test reached a real model provider."""


def pytest_collection_modifyitems(config, items):
    if RUN_LIVE_MODEL_TESTS:
        return
    skip = pytest.mark.skip(reason="calls a real model provider: set RUN_LIVE_MODEL_TESTS=1")
    for item in items:
        if item.get_closest_marker("live_model"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_live_model_calls(request, monkeypatch):
    if RUN_LIVE_MODEL_TESTS and request.node.get_closest_marker("live_model"):
        yield
        return
    reached = request.node.live_model_calls = []
    message = "a unit test reached the OpenAI API: give it a fake model, or mark it live_model"

    def refuse(self, *args, **kwargs):
        reached.append(type(self).__name__)
        raise LiveModelCallBlocked(message)

    async def refuse_async(self, *args, **kwargs):
        reached.append(type(self).__name__)
        raise LiveModelCallBlocked(message)

    monkeypatch.setattr(openai._base_client.SyncAPIClient, "request", refuse)
    monkeypatch.setattr(openai._base_client.AsyncAPIClient, "request", refuse_async)
    yield
    if reached:
        pytest.fail(f"{request.node.nodeid}: {message} ({len(reached)} request(s))", pytrace=False)


@pytest.fixture(autouse=True)
def fake_store_embeddings(request, monkeypatch):
    """The LangGraph store embeds what it saves (an article, a brand voice) through OpenAI's
    embeddings API. A unit test gets a fake of the same size, so saving still goes through the
    store and no provider is called. A live_model test, when those run, keeps the real one."""
    if RUN_LIVE_MODEL_TESTS and request.node.get_closest_marker("live_model"):
        return
    from langchain_core.embeddings import DeterministicFakeEmbedding

    monkeypatch.setattr(
        "src.flow.store.rext_store.init_embeddings",
        lambda *args, **kwargs: DeterministicFakeEmbedding(size=1536),
    )
