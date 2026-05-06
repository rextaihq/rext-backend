"""
Pytest configuration and shared fixtures for all tests.
"""

import os
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import ASGITransport, AsyncClient

# Prevent MinIO/S3 bucket checks at import time during tests.
os.environ.setdefault("REXT_STORAGE_SKIP_BUCKET_CHECK", "1")

from src.api.database.base import Base
from src.api.server import app
from src.api.database.async_database import get_async_db

from src.api.config import get_settings

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
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as ac:
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
        UserFactory, WorkspaceFactory, WorkspaceMemberFactory,
        ContentFactory, RoleFactory, InvitationFactory,
        KnowledgeBaseFactory, WebsiteFactory, KnowledgeFilesFactory, 
        TextKnowledgeFactory, PersonaFactory
    )

    # Set session for all factories
    UserFactory._session = db_session
    WorkspaceFactory._session = db_session
    WorkspaceMemberFactory._session = db_session
    ContentFactory._session = db_session
    RoleFactory._session = db_session
    InvitationFactory._session = db_session
    KnowledgeBaseFactory._session = db_session
    WebsiteFactory._session = db_session
    KnowledgeFilesFactory._session = db_session
    TextKnowledgeFactory._session = db_session
    PersonaFactory._session = db_session

    yield {
        "user": UserFactory,
        "workspace": WorkspaceFactory,
        "workspace_member": WorkspaceMemberFactory,
        "content": ContentFactory,
        "role": RoleFactory,
        "invitation": InvitationFactory,
        "knowledge_base": KnowledgeBaseFactory,
        "website": WebsiteFactory,
        "knowledge_file": KnowledgeFilesFactory,
        "text_knowledge": TextKnowledgeFactory,
        "persona": PersonaFactory,
    }

    # Cleanup is handled by db_session rollback


@pytest.fixture
def allow_permissions(monkeypatch):
    async def _allow(*args, **kwargs):
        return True

    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", _allow)
    monkeypatch.setattr("src.utils.rbac_utils.check_any_permission", _allow)
