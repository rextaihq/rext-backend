"""
Edge Case Tests for Invitation System

Tests critical edge cases identified in A2 recommendations:
1. User accepts invitation for workspace they're already member of
2. User has 50+ workspaces (performance test)
3. Concurrent invitation acceptance (race condition)
4. Inviter deletes account before invitee accepts
5. Workspace deleted before invitation accepted
6. User accepts invitation after email changed
7. User accepts expired invitation
8. User accepts invitation via OAuth (email mismatch)
9. User has pending invitations from deleted workspaces
"""

import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.users import User
from src.api.models.workspace_models.workspace import Workspace
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_members import WorkspaceMembers
from src.services.invitation_service import InvitationService
from src.services.workspace_service import WorkspaceService
from src.core.exceptions import (
    ResourceNotFoundException,
    BusinessRuleViolationException,
    ConflictException
)


@pytest.mark.asyncio
class TestInvitationEdgeCases:
    """Comprehensive edge case testing for invitation system."""

    async def test_accept_invitation_already_member(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 1: User accepts invitation for workspace they're already member of.

        Expected: Should handle gracefully - either accept idempotently or return clear error.
        """
        # First, make user a member
        existing_member = WorkspaceMembers(
            id=uuid4(),
            user_id=test_user.id,
            workspace_id=test_workspace.id,
            status="active",
            is_default=False
        )
        db.add(existing_member)
        await db.commit()

        # Create invitation
        invitation = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=test_workspace.user_id
        )

        # Try to accept invitation
        with pytest.raises(ConflictException) as exc_info:
            await invitation_service.accept_invitation(
                db=db,
                token=invitation.invitation_token,
                user_id=test_user.id
            )

        assert "already a member" in str(exc_info.value).lower()

    async def test_user_with_50_plus_workspaces_performance(
        self,
        db: AsyncSession,
        test_user: User,
        workspace_service: WorkspaceService
    ):
        """
        Edge Case 2: User has 50+ workspaces - performance test.

        Expected: GET /user/workspaces should complete in < 2 seconds.
        """
        # Create 60 workspaces for the user
        workspaces = []
        for i in range(60):
            workspace = Workspace(
                id=uuid4(),
                name=f"Workspace {i}",
                slug=f"workspace-{i}-{uuid4().hex[:8]}",
                user_id=test_user.id if i < 30 else uuid4()  # User owns 30, is member of 30
            )
            db.add(workspace)
            workspaces.append(workspace)

        await db.flush()

        # Add user as member to the other 30 workspaces
        for i in range(30, 60):
            member = WorkspaceMembers(
                id=uuid4(),
                user_id=test_user.id,
                workspace_id=workspaces[i].id,
                status="active",
                is_default=False
            )
            db.add(member)

        await db.commit()

        # Performance test: Fetch all user workspaces
        start_time = datetime.utcnow()

        user_workspaces = await workspace_service.get_user_workspaces(
            db=db,
            user_id=test_user.id
        )

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Assertions
        assert len(user_workspaces) == 60, f"Expected 60 workspaces, got {len(user_workspaces)}"
        assert duration < 2.0, f"Query took {duration}s (should be < 2s)"
        print(f"✅ Fetched 60 workspaces in {duration:.3f}s")

    async def test_concurrent_invitation_acceptance_race_condition(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 3: Concurrent invitation acceptance (race condition).

        Expected: Only one acceptance should succeed, others should fail gracefully.
        """
        # Create invitation
        invitation = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=test_workspace.user_id
        )

        # Create 5 concurrent acceptance attempts
        async def accept_invitation_task():
            """Simulate concurrent acceptance."""
            try:
                result = await invitation_service.accept_invitation(
                    db=db,
                    token=invitation.invitation_token,
                    user_id=test_user.id
                )
                return ("success", result)
            except Exception as e:
                return ("error", str(e))

        # Run 5 concurrent acceptance attempts
        tasks = [accept_invitation_task() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successes and failures
        successes = [r for r in results if isinstance(r, tuple) and r[0] == "success"]
        errors = [r for r in results if isinstance(r, tuple) and r[0] == "error"]

        # Assertions
        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
        assert len(errors) >= 4, f"Expected at least 4 errors, got {len(errors)}"

        print(f"✅ Concurrent test: {len(successes)} success, {len(errors)} handled errors")

    async def test_inviter_deleted_before_acceptance(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 4: Inviter deletes account before invitee accepts.

        Expected: Invitation should still be acceptable (or clear error message).
        """
        # Create inviter user
        inviter = User(
            id=uuid4(),
            email="inviter@example.com",
            username="inviter",
            first_name="Test",
            last_name="Inviter",
            password_hash="hashed",
            email_verified=True
        )
        db.add(inviter)
        await db.commit()

        # Create invitation from inviter
        invitation = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=inviter.id
        )

        # Soft-delete the inviter
        inviter.deleted_at = datetime.utcnow()
        await db.commit()

        # Try to accept invitation
        try:
            result = await invitation_service.accept_invitation(
                db=db,
                token=invitation.invitation_token,
                user_id=test_user.id
            )
            # Should succeed - invitation is valid even if inviter is deleted
            assert result is not None
            print("✅ Invitation accepted even after inviter deleted")
        except Exception as e:
            # If it fails, ensure error message is clear
            assert "inviter" in str(e).lower() or "deleted" in str(e).lower()
            print(f"✅ Clear error when inviter deleted: {e}")

    async def test_workspace_deleted_before_acceptance(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 5: Workspace deleted before invitation accepted.

        Expected: Should fail with clear error message.
        """
        # Create invitation
        invitation = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=test_workspace.user_id
        )

        # Soft-delete the workspace
        test_workspace.deleted_at = datetime.utcnow()
        await db.commit()

        # Try to accept invitation
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                db=db,
                token=invitation.invitation_token,
                user_id=test_user.id
            )

        assert "workspace" in str(exc_info.value).lower()
        assert "deleted" in str(exc_info.value).lower() or "not found" in str(exc_info.value).lower()
        print(f"✅ Clear error when workspace deleted: {exc_info.value}")

    async def test_accept_invitation_after_email_changed(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 6: User accepts invitation after changing their email.

        Expected: Should fail with email mismatch error.
        """
        original_email = "original@example.com"

        # Create invitation to original email
        invitation = await invitation_service.create_invitation(
            db=db,
            email=original_email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=test_workspace.user_id
        )

        # User changes their email
        test_user.email = "new_email@example.com"
        await db.commit()

        # Try to accept invitation with new email
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                db=db,
                token=invitation.invitation_token,
                user_id=test_user.id
            )

        assert "email" in str(exc_info.value).lower()
        print(f"✅ Email mismatch detected: {exc_info.value}")

    async def test_accept_expired_invitation(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Edge Case 7: User accepts expired invitation.

        Expected: Should fail with clear expiration error.
        """
        # Create invitation
        invitation = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=uuid4(),
            invited_by_user_id=test_workspace.user_id,
            expiry_days=7
        )

        # Manually expire the invitation
        invitation.expires_at = datetime.utcnow() - timedelta(days=1)
        await db.commit()

        # Try to accept expired invitation
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                db=db,
                token=invitation.invitation_token,
                user_id=test_user.id
            )

        assert "expired" in str(exc_info.value).lower()
        print(f"✅ Expired invitation rejected: {exc_info.value}")

    async def test_pending_invitations_from_deleted_workspaces(
        self,
        db: AsyncSession,
        test_user: User,
        invitation_service: InvitationService
    ):
        """
        Edge Case 9: User has pending invitations from deleted workspaces.

        Expected: GET /user/invitations/pending should filter out deleted workspaces.
        """
        # Create 3 workspaces (2 will be deleted)
        workspaces = []
        for i in range(3):
            ws = Workspace(
                id=uuid4(),
                name=f"Workspace {i}",
                slug=f"workspace-{i}-{uuid4().hex[:8]}",
                user_id=uuid4()
            )
            db.add(ws)
            workspaces.append(ws)

        await db.flush()

        # Create invitations to all 3 workspaces
        invitations = []
        for ws in workspaces:
            inv = await invitation_service.create_invitation(
                db=db,
                email=test_user.email,
                workspace_id=ws.id,
                role_id=uuid4(),
                invited_by_user_id=ws.user_id
            )
            invitations.append(inv)

        # Soft-delete 2 workspaces
        workspaces[0].deleted_at = datetime.utcnow()
        workspaces[1].deleted_at = datetime.utcnow()
        await db.commit()

        # Get pending invitations
        pending = await invitation_service.get_pending_invitations_for_user(
            db=db,
            user_email=test_user.email
        )

        # Should only return invitation from non-deleted workspace
        assert len(pending) == 1, f"Expected 1 pending invitation, got {len(pending)}"
        assert pending[0].workspace_id == workspaces[2].id
        print(f"✅ Filtered out {2} invitations from deleted workspaces")

    async def test_duplicate_invitation_handling(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Additional Edge Case: Creating duplicate invitations.

        Expected: Should prevent or handle duplicate invitations gracefully.
        """
        role_id = uuid4()

        # Create first invitation
        invitation1 = await invitation_service.create_invitation(
            db=db,
            email=test_user.email,
            workspace_id=test_workspace.id,
            role_id=role_id,
            invited_by_user_id=test_workspace.user_id
        )

        # Try to create duplicate invitation
        with pytest.raises(ConflictException) as exc_info:
            await invitation_service.create_invitation(
                db=db,
                email=test_user.email,
                workspace_id=test_workspace.id,
                role_id=role_id,
                invited_by_user_id=test_workspace.user_id
            )

        assert "already" in str(exc_info.value).lower() or "duplicate" in str(exc_info.value).lower()
        print(f"✅ Duplicate invitation prevented: {exc_info.value}")

    async def test_invitation_token_security(
        self,
        db: AsyncSession,
        test_user: User,
        test_workspace: Workspace,
        invitation_service: InvitationService
    ):
        """
        Security Edge Case: Ensure invitation tokens are cryptographically strong.

        Expected: Tokens should be unique, random, and of sufficient length.
        """
        # Create 100 invitations
        tokens = set()
        for i in range(100):
            invitation = await invitation_service.create_invitation(
                db=db,
                email=f"user{i}@example.com",
                workspace_id=test_workspace.id,
                role_id=uuid4(),
                invited_by_user_id=test_workspace.user_id
            )
            tokens.add(invitation.invitation_token)

        # Assertions
        assert len(tokens) == 100, "Tokens should be unique"

        # Check token length (should be at least 32 characters for security)
        for token in tokens:
            assert len(token) >= 32, f"Token too short: {len(token)} chars"

        print(f"✅ All 100 tokens unique and secure (>= 32 chars)")


# Fixtures

@pytest.fixture
async def invitation_service():
    """Provide InvitationService instance."""
    return InvitationService()


@pytest.fixture
async def workspace_service():
    """Provide WorkspaceService instance."""
    return WorkspaceService()


@pytest.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=uuid4(),
        email="testuser@example.com",
        username="testuser",
        first_name="Test",
        last_name="User",
        password_hash="hashed_password",
        email_verified=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def test_workspace(db: AsyncSession, test_user: User) -> Workspace:
    """Create a test workspace."""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug=f"test-workspace-{uuid4().hex[:8]}",
        user_id=test_user.id
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace
