"""
Unit tests for InvitationService.

Tests invitation business logic including creation, acceptance,
revocation, and expiry management.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timedelta

from src.services.invitation_service import InvitationService
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.user_models.roles import Role
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    RextValidationException,
    BusinessRuleViolationException
)


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def invitation_service(mock_db):
    """Create an InvitationService instance with mock db."""
    return InvitationService(db=mock_db)


@pytest.fixture
def sample_workspace():
    """Create a sample workspace."""
    workspace = MagicMock(spec=WorkspaceModel)
    workspace.id = uuid4()
    workspace.name = "Test Workspace"
    return workspace


@pytest.fixture
def sample_role():
    """Create a sample role."""
    role = MagicMock(spec=Role)
    role.id = uuid4()
    role.name = "Member"
    return role


@pytest.fixture
def sample_user():
    """Create a sample user."""
    user = MagicMock(spec=Users)
    user.id = uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def sample_invitation(sample_workspace, sample_role, sample_user):
    """Create a sample invitation."""
    invitation = MagicMock(spec=UserInvitations)
    invitation.id = uuid4()
    invitation.email = "invitee@example.com"
    invitation.workspace_id = sample_workspace.id
    invitation.role_id = sample_role.id
    invitation.invited_by_user_id = sample_user.id
    invitation.invitation_token = "test_token_123"
    invitation.status = "pending"
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invitation.created_at = datetime.now(timezone.utc)
    return invitation


class TestGenerateInvitationToken:
    """Tests for _generate_invitation_token method."""

    def test_generate_invitation_token_returns_string(self, invitation_service):
        """Test that token generation returns a string."""
        email = "test@example.com"
        workspace_id = uuid4()
        
        token = invitation_service._generate_invitation_token(email, workspace_id)
        
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_invitation_token_is_unique(self, invitation_service):
        """Test that each token generation produces unique tokens."""
        email = "test@example.com"
        workspace_id = uuid4()
        
        token1 = invitation_service._generate_invitation_token(email, workspace_id)
        token2 = invitation_service._generate_invitation_token(email, workspace_id)
        
        assert token1 != token2

    def test_generate_invitation_token_different_inputs(self, invitation_service):
        """Test that different inputs produce different tokens."""
        token1 = invitation_service._generate_invitation_token("email1@example.com", uuid4())
        token2 = invitation_service._generate_invitation_token("email2@example.com", uuid4())
        
        assert token1 != token2


class TestCreateInvitation:
    """Tests for create_invitation method."""

    @pytest.mark.asyncio
    async def test_create_invitation_success(
        self, invitation_service, mock_db, sample_workspace, sample_role, sample_user
    ):
        """Test successful invitation creation."""
        # Arrange
        email = "new@example.com"
        workspace_id = sample_workspace.id
        role_id = sample_role.id
        user_id = sample_user.id

        # Mock database queries
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role
        
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = sample_user
        
        invitation_check_result = MagicMock()
        invitation_check_result.scalar_one_or_none.return_value = None
        
        user_check_result = MagicMock()
        user_check_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[
            workspace_result,
            role_result,
            inviter_result,
            invitation_check_result,
            user_check_result
        ])

        # Act
        result = await invitation_service.create_invitation(
            email=email,
            workspace_id=workspace_id,
            role_id=role_id,
            invited_by_user_id=user_id,
            expiry_days=7
        )

        # Assert
        assert mock_db.add.called
        assert mock_db.flush.call_count >= 1
        assert mock_db.refresh.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_invitation_validates_expiry_days_too_small(
        self, invitation_service, sample_workspace, sample_role, sample_user
    ):
        """Test that expiry_days must be at least 1."""
        with pytest.raises(RextValidationException) as exc_info:
            await invitation_service.create_invitation(
            email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=sample_role.id,
                invited_by_user_id=sample_user.id,
                expiry_days=0
            )
        
        assert "between 1 and 30" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_invitation_validates_expiry_days_too_large(
        self, invitation_service, sample_workspace, sample_role, sample_user
    ):
        """Test that expiry_days must be at most 30."""
        with pytest.raises(RextValidationException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=sample_role.id,
                invited_by_user_id=sample_user.id,
                expiry_days=31
            )
        
        assert "between 1 and 30" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_invitation_workspace_not_found(
        self, invitation_service, mock_db, sample_role, sample_user
    ):
        """Test that missing workspace raises exception."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=workspace_result)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=uuid4(),
                role_id=sample_role.id,
                invited_by_user_id=sample_user.id
            )
        
        assert exc_info.value.context['resource_type'] == "Workspace"

    @pytest.mark.asyncio
    async def test_create_invitation_role_not_found(
        self, invitation_service, mock_db, sample_workspace, sample_user
    ):
        """Test that missing role raises exception."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[workspace_result, role_result])

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=uuid4(),
                invited_by_user_id=sample_user.id
            )
        
        assert exc_info.value.context['resource_type'] == "Role"

    @pytest.mark.asyncio
    async def test_create_invitation_inviter_not_found(
        self, invitation_service, mock_db, sample_workspace, sample_role
    ):
        """Test that missing inviter raises exception."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role
        
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[
            workspace_result, role_result, inviter_result
        ])

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=sample_role.id,
                invited_by_user_id=uuid4()
            )
        
        assert exc_info.value.context['resource_type'] == "User"

    @pytest.mark.asyncio
    async def test_create_invitation_duplicate_active_invitation(
        self, invitation_service, mock_db, sample_workspace, sample_role, sample_user
    ):
        """Test that duplicate active invitation raises exception."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role
        
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = sample_user
        
        # Existing invitation that hasn't expired
        existing_invitation = MagicMock()
        existing_invitation.status = "pending"
        existing_invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=5)
        
        invitation_check_result = MagicMock()
        invitation_check_result.scalar_one_or_none.return_value = existing_invitation

        mock_db.execute = AsyncMock(side_effect=[
            workspace_result, role_result, inviter_result, invitation_check_result
        ])

        with pytest.raises(DuplicateResourceException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=sample_role.id,
                invited_by_user_id=sample_user.id
            )
        
        assert exc_info.value.context['resource_type'] == "Invitation"

    @pytest.mark.asyncio
    async def test_create_invitation_auto_expires_old_invitation(
        self, invitation_service, mock_db, sample_workspace, sample_role, sample_user
    ):
        """Test that expired pending invitation is auto-expired."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role
        
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = sample_user
        
        # Existing expired invitation
        expired_invitation = MagicMock()
        expired_invitation.status = "pending"
        expired_invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        
        invitation_check_result = MagicMock()
        invitation_check_result.scalar_one_or_none.return_value = expired_invitation
        
        user_check_result = MagicMock()
        user_check_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[
            workspace_result, role_result, inviter_result,
            invitation_check_result, user_check_result
        ])

        # Should succeed and auto-expire the old one
        result = await invitation_service.create_invitation(
            email="test@example.com",
            workspace_id=sample_workspace.id,
            role_id=sample_role.id,
            invited_by_user_id=sample_user.id
        )

        assert expired_invitation.status == "expired"
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_invitation_user_already_member(
        self, invitation_service, mock_db, sample_workspace, sample_role, sample_user
    ):
        """Test that invitation to existing member raises exception."""
        workspace_result = MagicMock()
        workspace_result.scalar_one_or_none.return_value = sample_workspace
        
        role_result = MagicMock()
        role_result.scalar_one_or_none.return_value = sample_role
        
        inviter_result = MagicMock()
        inviter_result.scalar_one_or_none.return_value = sample_user
        
        invitation_check_result = MagicMock()
        invitation_check_result.scalar_one_or_none.return_value = None
        
        existing_user = MagicMock()
        existing_user.id = uuid4()
        existing_user.email = "test@example.com"
        
        user_check_result = MagicMock()
        user_check_result.scalar_one_or_none.return_value = existing_user
        
        existing_membership = MagicMock()
        membership_check_result = MagicMock()
        membership_check_result.scalar_one_or_none.return_value = existing_membership

        mock_db.execute = AsyncMock(side_effect=[
            workspace_result, role_result, inviter_result,
            invitation_check_result, user_check_result, membership_check_result
        ])

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.create_invitation(
                email="test@example.com",
                workspace_id=sample_workspace.id,
                role_id=sample_role.id,
                invited_by_user_id=sample_user.id
            )
        
        assert "already a member" in str(exc_info.value)


class TestGetInvitationById:
    """Tests for get_invitation_by_id method."""

    @pytest.mark.asyncio
    async def test_get_invitation_by_id_success(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test successful invitation retrieval by ID."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await invitation_service.get_invitation_by_id(sample_invitation.id)

        assert result == sample_invitation

    @pytest.mark.asyncio
    async def test_get_invitation_by_id_not_found(self, invitation_service, mock_db):
        """Test that missing invitation raises exception."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.get_invitation_by_id(uuid4())
        
        assert exc_info.value.context['resource_type'] == "Invitation"


class TestGetInvitationByToken:
    """Tests for get_invitation_by_token method."""

    @pytest.mark.asyncio
    async def test_get_invitation_by_token_success(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test successful invitation retrieval by token."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await invitation_service.get_invitation_by_token("test_token")

        assert result == sample_invitation

    @pytest.mark.asyncio
    async def test_get_invitation_by_token_not_found(self, invitation_service, mock_db):
        """Test that missing invitation raises exception."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.get_invitation_by_token("invalid_token")
        
        assert exc_info.value.context['resource_type'] == "Invitation"


class TestGetWorkspaceInvitations:
    """Tests for get_workspace_invitations method."""

    @pytest.mark.asyncio
    async def test_get_workspace_invitations_all(
        self, invitation_service, mock_db, sample_invitation, sample_workspace
    ):
        """Test retrieving all workspace invitations."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sample_invitation]
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await invitation_service.get_workspace_invitations(
            workspace_id=sample_workspace.id
        )

        assert len(result) == 1
        assert result[0] == sample_invitation

    @pytest.mark.asyncio
    async def test_get_workspace_invitations_filtered_by_status(
        self, invitation_service, mock_db, sample_workspace
    ):
        """Test retrieving invitations filtered by status."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await invitation_service.get_workspace_invitations(
            workspace_id=sample_workspace.id,
            status="accepted"
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_workspace_invitations_with_pagination(
        self, invitation_service, mock_db, sample_workspace
    ):
        """Test retrieving invitations with pagination."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await invitation_service.get_workspace_invitations(
            workspace_id=sample_workspace.id,
            limit=10,
            offset=20
        )

        assert isinstance(result, list)


class TestAcceptInvitation:
    """Tests for accept_invitation method."""

    @pytest.mark.asyncio
    async def test_accept_invitation_success(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test successful invitation acceptance."""
        # Mock get_invitation_by_id
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        
        # Mock user lookup
        user = MagicMock()
        user.id = sample_user.id
        user.email = sample_invitation.email
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        
        # Mock membership check (no existing membership)
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[
            invitation_result, user_result, membership_result
        ])

        result = await invitation_service.accept_invitation(
            invitation_id=sample_invitation.id,
            user_id=sample_user.id
        )

        assert "invitation_id" in result
        assert "membership_id" in result
        assert sample_invitation.status == "accepted"
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_accept_invitation_not_pending(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test that non-pending invitation cannot be accepted."""
        sample_invitation.status = "accepted"
        
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                invitation_id=sample_invitation.id,
                user_id=sample_user.id
            )
        
        assert "cannot accept" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_accept_invitation_expired(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test that expired invitation cannot be accepted."""
        sample_invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                invitation_id=sample_invitation.id,
                user_id=sample_user.id
            )
        
        assert "expired" in str(exc_info.value)
        assert sample_invitation.status == "expired"

    @pytest.mark.asyncio
    async def test_accept_invitation_user_not_found(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test that missing user raises exception."""
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[invitation_result, user_result])

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await invitation_service.accept_invitation(
                invitation_id=sample_invitation.id,
                user_id=uuid4()
            )
        
        assert exc_info.value.context['resource_type'] == "User"

    @pytest.mark.asyncio
    async def test_accept_invitation_email_mismatch(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test that email mismatch raises exception."""
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        
        wrong_user = MagicMock()
        wrong_user.id = uuid4()
        wrong_user.email = "different@example.com"
        
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = wrong_user

        mock_db.execute = AsyncMock(side_effect=[invitation_result, user_result])

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                invitation_id=sample_invitation.id,
                user_id=wrong_user.id
            )
        
        assert "email does not match" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_accept_invitation_already_member(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test that existing member raises exception."""
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        
        user = MagicMock()
        user.id = sample_user.id
        user.email = sample_invitation.email
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        
        existing_membership = MagicMock()
        membership_result = MagicMock()
        membership_result.scalar_one_or_none.return_value = existing_membership

        mock_db.execute = AsyncMock(side_effect=[
            invitation_result, user_result, membership_result
        ])

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.accept_invitation(
                invitation_id=sample_invitation.id,
                user_id=sample_user.id
            )
        
        assert "already a member" in str(exc_info.value)
        assert sample_invitation.status == "accepted"


class TestRevokeInvitation:
    """Tests for revoke_invitation method."""

    @pytest.mark.asyncio
    async def test_revoke_invitation_success(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test successful invitation revocation."""
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        result = await invitation_service.revoke_invitation(
            invitation_id=sample_invitation.id,
            revoked_by_user_id=sample_user.id
        )

        assert result.status == "revoked"

    @pytest.mark.asyncio
    async def test_revoke_invitation_not_pending(
        self, invitation_service, mock_db, sample_invitation, sample_user
    ):
        """Test that non-pending invitation cannot be revoked."""
        sample_invitation.status = "accepted"
        
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.revoke_invitation(
                invitation_id=sample_invitation.id,
                revoked_by_user_id=sample_user.id
            )
        
        assert "Cannot revoke" in str(exc_info.value)


class TestExpireOldInvitations:
    """Tests for expire_old_invitations method."""

    @pytest.mark.asyncio
    async def test_expire_old_invitations_none_to_expire(
        self, invitation_service, mock_db
    ):
        """Test expiring when no invitations are expired."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        count = await invitation_service.expire_old_invitations()

        assert count == 0
        assert not mock_db.flush.called

    @pytest.mark.asyncio
    async def test_expire_old_invitations_expires_multiple(
        self, invitation_service, mock_db
    ):
        """Test expiring multiple old invitations."""
        inv1 = MagicMock()
        inv1.status = "pending"
        inv2 = MagicMock()
        inv2.status = "pending"
        
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [inv1, inv2]
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        count = await invitation_service.expire_old_invitations()

        assert count == 2
        assert inv1.status == "expired"
        assert inv2.status == "expired"
        assert mock_db.flush.called

    @pytest.mark.asyncio
    async def test_expire_old_invitations_respects_batch_size(
        self, invitation_service, mock_db
    ):
        """Test that batch size is respected."""
        invitations = [MagicMock() for _ in range(5)]
        
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = invitations
        
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        
        mock_db.execute = AsyncMock(return_value=result_mock)

        count = await invitation_service.expire_old_invitations(batch_size=5)

        assert count == 5


class TestResendInvitation:
    """Tests for resend_invitation method."""

    @pytest.mark.asyncio
    async def test_resend_invitation_success(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test successful invitation resend."""
        original_token = sample_invitation.invitation_token
        original_expiry = sample_invitation.expires_at
        
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        result = await invitation_service.resend_invitation(
            invitation_id=sample_invitation.id,
            extend_days=7
        )

        assert result.invitation_token != original_token
        assert result.expires_at > original_expiry

    @pytest.mark.asyncio
    async def test_resend_invitation_not_pending(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test that non-pending invitation cannot be resent."""
        sample_invitation.status = "accepted"
        
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await invitation_service.resend_invitation(
                invitation_id=sample_invitation.id
            )
        
        assert "Cannot resend" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_resend_invitation_custom_extend_days(
        self, invitation_service, mock_db, sample_invitation
    ):
        """Test resending with custom extend days."""
        invitation_result = MagicMock()
        invitation_result.scalar_one_or_none.return_value = sample_invitation
        mock_db.execute = AsyncMock(return_value=invitation_result)

        result = await invitation_service.resend_invitation(
            invitation_id=sample_invitation.id,
            extend_days=14
        )

        # Verify expiry is approximately 14 days in the future
        expected_expiry = datetime.now(timezone.utc) + timedelta(days=14)
        time_diff = abs((result.expires_at - expected_expiry).total_seconds())
        assert time_diff < 5  # Allow 5 seconds difference for test execution time
