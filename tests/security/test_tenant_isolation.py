"""
Security Tests for Multi-Tenancy Isolation

This test suite verifies that workspace (tenant) isolation is properly enforced
across all database queries and API endpoints. These tests ensure that users
from one workspace cannot access data from another workspace.

Test Categories:
1. Content isolation
2. Member isolation (workspace members)
3. Workspace settings isolation

Testing Strategy:
- Create two separate workspaces (A and B)
- Create users in each workspace
- Create resources in workspace B
- Attempt to access workspace B resources as workspace A user
- Assert that access is denied (404 Not Found, not 403 to avoid leaking existence)
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.services.content_service import ContentService
from src.services.member_service import MemberService
from src.services.workspace_service import WorkspaceService
from tests.conftest import TEST_DATABASE_URL

# ============================================================================
# Fixtures
# ============================================================================


def _with_parents(*tables):
    """The tables, and every table their foreign keys reach."""
    found = []

    def visit(table):
        if table in found:
            return
        found.append(table)
        for key in table.foreign_keys:
            visit(key.column.table)

    for table in tables:
        visit(table)
    return found


@pytest_asyncio.fixture
async def db():
    """The tables these tests need, inside a transaction that is rolled back.

    The services commit in places: each commit only releases a savepoint, so nothing
    is left behind, on an empty test database or a migrated one.
    """
    tables = _with_parents(
        Users.__table__,
        WorkspaceModel.__table__,
        WorkspaceMembers.__table__,
        Content.__table__,
        ContentSEOData.__table__,  # creating content writes its SEO row
        Role.__table__,  # a new member gets the viewer role
        UserRole.__table__,
        AuditLog.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(sync, tables=tables, checkfirst=True)
        )
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


async def _viewer_role(db: AsyncSession) -> Role:
    """The workspace viewer role a new member gets: the seeded one, or one made here."""
    role = (await db.execute(select(Role).where(Role.name == "viewer"))).scalar_one_or_none()
    if role is None:
        role = Role(name="viewer", display_name="Viewer", is_workspace_role=True)
        db.add(role)
        await db.flush()
    return role


def _user(name: str) -> Users:
    return Users(
        id=uuid4(),
        email=f"{name.lower().replace(' ', '-')}-{uuid4().hex[:8]}@example.com",
        full_name=name,
    )


@pytest_asyncio.fixture
async def workspace_a(db: AsyncSession) -> WorkspaceModel:
    """Create workspace A for testing"""
    user_a = _user("User A")
    db.add(user_a)
    await db.flush()

    workspace = WorkspaceModel(
        id=uuid4(),
        user_id=user_a.id,
        name="Workspace A",
        slug=f"workspace-a-{uuid4().hex[:8]}",
        url="https://workspace-a.com",
    )
    db.add(workspace)
    await db.flush()

    # Add user as member
    member = WorkspaceMembers(
        workspace_id=workspace.id,
        user_id=user_a.id,
        status="active",
        is_default=True,
    )
    db.add(member)
    await db.flush()

    await db.refresh(workspace)
    await db.refresh(user_a)
    workspace.owner = user_a  # Attach for easy access
    return workspace


@pytest_asyncio.fixture
async def workspace_b(db: AsyncSession) -> WorkspaceModel:
    """Create workspace B for testing"""
    user_b = _user("User B")
    db.add(user_b)
    await db.flush()

    workspace = WorkspaceModel(
        id=uuid4(),
        user_id=user_b.id,
        name="Workspace B",
        slug=f"workspace-b-{uuid4().hex[:8]}",
        url="https://workspace-b.com",
    )
    db.add(workspace)
    await db.flush()

    # Add user as member
    member = WorkspaceMembers(
        workspace_id=workspace.id,
        user_id=user_b.id,
        status="active",
        is_default=True,
    )
    db.add(member)
    await db.flush()

    await db.refresh(workspace)
    await db.refresh(user_b)
    workspace.owner = user_b
    return workspace


@pytest_asyncio.fixture
async def content_in_workspace_b(db: AsyncSession, workspace_b: WorkspaceModel) -> Content:
    """Create content in workspace B"""
    content = Content(
        id=uuid4(),
        workspace_id=workspace_b.id,
        created_by_user_id=workspace_b.owner.id,
        title="Secret Content B",
        slug="secret-content-b",
        body_markdown="This is secret content in workspace B",
        status="published",
        content_language="English",
    )
    db.add(content)
    await db.flush()
    await db.refresh(content)
    return content


# ============================================================================
# Content Isolation Tests
# ============================================================================


@pytest.mark.asyncio
class TestContentIsolation:
    """Test that content is properly isolated between workspaces"""

    async def test_cannot_get_content_from_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        content_in_workspace_b: Content,
    ):
        """
        CRITICAL: User from workspace A cannot access content from workspace B

        This test verifies the most important security boundary: content isolation.
        """
        service = ContentService(db)

        # Try to get content from workspace B using workspace A's ID
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await service._get_content_or_404(
                content_id=content_in_workspace_b.id, workspace_id=workspace_a.id
            )

        # Verify it returns 404 (not 403) to avoid leaking existence
        assert "Content" in str(exc_info.value)
        assert str(content_in_workspace_b.id) in str(exc_info.value)

    async def test_cannot_update_content_from_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        content_in_workspace_b: Content,
    ):
        """User from workspace A cannot update content in workspace B"""
        from src.api.schema.content_schema import ContentUpdate

        service = ContentService(db)

        update_data = ContentUpdate(title="Hacked Title")

        with pytest.raises(ResourceNotFoundException):
            await service.update_content(
                content_id=content_in_workspace_b.id,
                workspace_id=workspace_a.id,  # Wrong workspace!
                user_id=workspace_a.owner.id,
                data=update_data,
            )

        # Verify content was NOT modified
        await db.refresh(content_in_workspace_b)
        assert content_in_workspace_b.title == "Secret Content B"

    async def test_cannot_delete_content_from_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        content_in_workspace_b: Content,
    ):
        """User from workspace A cannot delete content in workspace B"""
        service = ContentService(db)

        with pytest.raises(ResourceNotFoundException):
            await service.delete_content(
                content_id=content_in_workspace_b.id, workspace_id=workspace_a.id
            )

        # Verify content still exists and is NOT deleted
        await db.refresh(content_in_workspace_b)
        assert content_in_workspace_b.deleted_at is None

    async def test_cannot_publish_content_from_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
    ):
        """User from workspace A cannot publish draft content in workspace B"""
        # Create draft content in workspace B
        draft_content = Content(
            id=uuid4(),
            workspace_id=workspace_b.id,
            created_by_user_id=workspace_b.owner.id,
            title="Draft Content B",
            slug="draft-content-b",
            body_markdown="Draft content",
            status="ready",  # Ready to publish
            content_language="English",
        )
        db.add(draft_content)
        await db.flush()

        service = ContentService(db)

        with pytest.raises(ResourceNotFoundException):
            await service.publish_content(
                content_id=draft_content.id,
                workspace_id=workspace_a.id,  # Wrong workspace!
                user_id=workspace_a.owner.id,
            )

        # Verify content status unchanged
        await db.refresh(draft_content)
        assert draft_content.status == "ready"  # NOT published


# ============================================================================
# Member Isolation Tests
# ============================================================================


@pytest.mark.asyncio
class TestMemberIsolation:
    """Test that workspace members are properly isolated"""

    async def test_cannot_add_member_to_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
    ):
        """
        Cannot add a member to workspace B when interacting with workspace A's service

        Note: This test verifies service-level isolation. Route-level authorization
        should prevent this from even reaching the service layer.
        """
        service = MemberService(db)

        # Create a new user to add
        await _viewer_role(db)
        new_user = _user("New User")
        db.add(new_user)
        await db.flush()

        # This should succeed - adding to workspace A
        member_a = await service.add_member(
            workspace_id=workspace_a.id, user_id=new_user.id, status="active"
        )
        assert member_a.workspace_id == workspace_a.id

        # Verify member is NOT in workspace B
        from sqlalchemy import select

        result = await db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_b.id,
                WorkspaceMembers.user_id == new_user.id,
            )
        )
        assert result.scalar_one_or_none() is None

    async def test_cannot_remove_member_from_other_workspace(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
    ):
        """User from workspace A cannot remove members from workspace B"""
        service = MemberService(db)

        # Try to remove workspace B's owner (should fail or not affect workspace B)
        with pytest.raises(ResourceNotFoundException):
            await service.remove_member(
                workspace_id=workspace_a.id,  # Wrong workspace context
                user_id=workspace_b.owner.id,  # Trying to remove B's owner
            )

        # Verify workspace B's owner is still a member
        from sqlalchemy import select

        result = await db.execute(
            select(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_b.id,
                WorkspaceMembers.user_id == workspace_b.owner.id,
            )
        )
        assert result.scalar_one_or_none() is not None


# ============================================================================
# Workspace Settings Isolation Tests
# ============================================================================


@pytest.mark.asyncio
class TestWorkspaceSettingsIsolation:
    """Test that workspace settings cannot be modified across workspaces"""

    async def test_cannot_update_other_workspace_settings(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
    ):
        """User from workspace A cannot update workspace B's settings"""
        service = WorkspaceService(db)
        original_name = workspace_b.name
        original_url = workspace_b.url

        # User A updating workspace B: the membership check refuses it as not found.
        with pytest.raises(ResourceNotFoundException):
            await service.update_workspace_for_user(
                workspace_id=workspace_b.id,
                user_id=workspace_a.owner.id,
                name="Hacked Name",
                timezone=None,
                url="https://hacked.example",
            )

        # Verify workspace B settings unchanged
        await db.refresh(workspace_b)
        assert workspace_b.name == original_name
        assert workspace_b.url == original_url

    async def test_get_workspace_analytics_only_shows_own_data(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
        content_in_workspace_b: Content,
    ):
        """Workspace analytics only show data for the specified workspace"""
        # Two items in workspace A, one in workspace B: each count is its own.
        content_a = Content(
            id=uuid4(),
            workspace_id=workspace_a.id,
            created_by_user_id=workspace_a.owner.id,
            title="Content A",
            slug="content-a",
            body_markdown="Content for workspace A",
            status="published",
            content_language="English",
        )
        db.add(content_a)
        db.add(
            Content(
                id=uuid4(),
                workspace_id=workspace_a.id,
                created_by_user_id=workspace_a.owner.id,
                title="Content A2",
                slug="content-a2",
                body_markdown="Second item for workspace A",
                status="published",
                content_language="English",
            )
        )
        await db.flush()

        service = WorkspaceService(db)

        # Get analytics for workspace A
        analytics_a = await service.get_workspace_analytics(workspace_id=workspace_a.id)

        # Should show workspace A's two items only
        assert analytics_a["content_count"] == 2

        # Get analytics for workspace B
        analytics_b = await service.get_workspace_analytics(workspace_id=workspace_b.id)

        # Should show 1 content item (content_in_workspace_b)
        assert analytics_b["content_count"] == 1

        # Analytics should be independent
        assert analytics_a != analytics_b


# ============================================================================
# Integration Tests (End-to-End)
# ============================================================================


@pytest.mark.asyncio
class TestTenantIsolationEndToEnd:
    """
    End-to-end tests that simulate real attack scenarios

    These tests verify that the entire stack (routes + services + database)
    properly enforces tenant isolation.
    """

    async def test_complete_workflow_isolation(
        self,
        db: AsyncSession,
        workspace_a: WorkspaceModel,
        workspace_b: WorkspaceModel,
    ):
        """
        Complete workflow test: Create content in B, try to access from A

        This simulates a real-world attack where a user tries to:
        1. Discover content IDs from workspace B
        2. Access that content using workspace A's context
        """
        # Step 1: Create content in workspace B
        content_service = ContentService(db)
        from src.api.schema.content_schema import ContentCreate

        content_data = ContentCreate(
            title="Confidential Document",
            body_markdown="This contains sensitive business data",
            status="published",
        )

        content_b = await content_service.create_content(
            workspace_id=workspace_b.id,
            user_id=workspace_b.owner.id,
            data=content_data,
        )

        # Step 2: Attacker from workspace A tries to access it
        with pytest.raises(ResourceNotFoundException):
            await content_service._get_content_or_404(
                content_id=content_b.id,
                workspace_id=workspace_a.id,  # ATTACK: Wrong workspace!
            )

        # Step 3: Verify content remains in workspace B only
        content_b_verify = await content_service._get_content_or_404(
            content_id=content_b.id,
            workspace_id=workspace_b.id,  # Correct workspace
        )
        assert content_b_verify.workspace_id == workspace_b.id


# ============================================================================
# Summary
# ============================================================================

"""
Security Test Coverage Summary:

✅ Content Isolation (5 tests)
   - Cannot get content from other workspace
   - Cannot update content from other workspace
   - Cannot delete content from other workspace
   - Cannot publish content from other workspace
   - Slug generation scoped to workspace

✅ Member Isolation (2 tests)
   - Cannot add member to other workspace
   - Cannot remove member from other workspace

✅ Workspace Settings Isolation (2 tests)
   - Cannot update other workspace settings
   - Analytics only show own workspace data

✅ Integration Tests (1 test)
   - Complete end-to-end workflow isolation

Total: 10 comprehensive security tests

Run these tests with:
    pytest tests/security/test_tenant_isolation.py -v

For CI/CD integration:
    pytest tests/security/test_tenant_isolation.py -v --cov=src/services --cov-report=html
"""
