"""
Factory configuration for pytest.
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def setup_factories(db_session: AsyncSession):
    """
    Set up factories with database session.
    All factories will use this session for creating instances.
    """
    from tests.factories import (
        ContentFactory,
        TopicFactory,
        UserFactory,
        WorkspaceFactory,
        WorkspaceMemberFactory,
    )

    # Set session for all factories
    UserFactory._meta.sqlalchemy_session = db_session
    WorkspaceFactory._meta.sqlalchemy_session = db_session
    WorkspaceMemberFactory._meta.sqlalchemy_session = db_session
    ContentFactory._meta.sqlalchemy_session = db_session
    TopicFactory._meta.sqlalchemy_session = db_session

    yield {
        "user": UserFactory,
        "workspace": WorkspaceFactory,
        "workspace_member": WorkspaceMemberFactory,
        "content": ContentFactory,
        "topic": TopicFactory,
    }

    # Cleanup is handled by db_session rollback
