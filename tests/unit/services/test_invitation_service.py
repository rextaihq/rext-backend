"""
Unit tests for InvitationService.

Tests cover:
- create_invitation: Creating invitations with validation
- get_invitation_by_id: Retrieving invitations
- get_invitation_by_token: Token-based retrieval
- get_workspace_invitations: Listing invitations
- accept_invitation: Accepting and creating membership
- revoke_invitation: Revoking invitations
- expire_old_invitations: Batch expiry processing
- resend_invitation: Extending and regenerating tokens
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta

from src.services.invitation_service import InvitationService
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    WrextValidationException,
    BusinessRuleViolationException
)


@pytest.mark.unit
class TestInvitationServiceCreateInvitation:
    """Test create_invitation method"""

    async def test_create_invitation_success(self, db_session, setup_factories):
        """Should successfully create invitation"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.create_invitation(
            email="newuser@example.com",
            workspace_id=workspace.id,
            role_id=role.id,
            invited_by_user_id=inviter.id
        )

        # Assert
        assert result.email == "newuser@example.com"
        assert result.workspace_id == workspace.id
        assert result.role_id == role.id
        assert result.status == "pending"
        assert result.invitation_token is not None
        assert result.expires_at > datetime.utcnow()

    async def test_create_invitation_normalizes_email(self, db_session, setup_factories):
        """Should normalize email to lowercase"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.create_invitation(
            email="NewUser@EXAMPLE.COM",
            workspace_id=workspace.id,
            role_id=role.id,
            invited_by_user_id=inviter.id
        )

        # Assert
        assert result.email == "newuser@example.com"

    async def test_create_invitation_custom_expiry(self, db_session, setup_factories):
        """Should respect custom expiry days"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.create_invitation(
            email="test@example.com",
            workspace_id=workspace.id,
            role_id=role.id,
            invited_by_user_id=inviter.id,
            expiry_days=14
        )

        # Assert
        expected_expiry = datetime.utcnow() + timedelta(days=14)
        assert abs((result.expires_at - expected_expiry).total_seconds()) < 2

    async def test_create_invitation_invalid_expiry_days(self, db_session, setup_factories):
        """Should reject invalid expiry days"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(WrextValidationException) as exc_info:
            await service.create_invitation(
                email="test@example.com",
                workspace_id=workspace.id,
                role_id=role.id,
                invited_by_user_id=inviter.id,
                expiry_days=50  # Invalid
            )

        assert "between 1 and 30" in exc_info.value.message

    async def test_create_invitation_workspace_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if workspace doesn't exist"""
        # Arrange
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.create_invitation(
                email="test@example.com",
                workspace_id=uuid4(),
                role_id=role.id,
                invited_by_user_id=inviter.id
            )

    async def test_create_invitation_role_not_found(self, db_session, setup_factories):
        """Should raise ResourceNotFoundException if role doesn't exist"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        inviter = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.create_invitation(
                email="test@example.com",
                workspace_id=workspace.id,
                role_id=uuid4(),
                invited_by_user_id=inviter.id
            )

    async def test_create_invitation_duplicate_active(self, db_session, setup_factories):
        """Should raise DuplicateResourceException for active duplicate"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()

        # Create existing invitation
        await setup_factories["invitation"].create(
            email="existing@example.com",
            workspace_id=workspace.id,
            role_id=role.id,
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )

        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(DuplicateResourceException) as exc_info:
            await service.create_invitation(
                email="existing@example.com",
                workspace_id=workspace.id,
                role_id=role.id,
                invited_by_user_id=inviter.id
            )

        assert "already exists" in exc_info.value.message

    async def test_create_invitation_user_already_member(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if user already member"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        role = await setup_factories["role"].create()
        inviter = await setup_factories["user"].create()
        existing_user = await setup_factories["user"].create(
            email="member@example.com"
        )
        await setup_factories["workspace_member"].create(
            workspace_id=workspace.id,
            user_id=existing_user.id
        )

        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.create_invitation(
                email="member@example.com",
                workspace_id=workspace.id,
                role_id=role.id,
                invited_by_user_id=inviter.id
            )

        assert "already a member" in exc_info.value.message


@pytest.mark.unit
class TestInvitationServiceGetInvitation:
    """Test get invitation methods"""

    async def test_get_invitation_by_id_success(self, db_session, setup_factories):
        """Should retrieve invitation by ID"""
        # Arrange
        invitation = await setup_factories["invitation"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.get_invitation_by_id(invitation.id)

        # Assert
        assert result.id == invitation.id
        assert result.email == invitation.email

    async def test_get_invitation_by_id_not_found(self, db_session):
        """Should raise ResourceNotFoundException if not found"""
        # Arrange
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.get_invitation_by_id(uuid4())

    async def test_get_invitation_by_token_success(self, db_session, setup_factories):
        """Should retrieve invitation by token"""
        # Arrange
        invitation = await setup_factories["invitation"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.get_invitation_by_token(invitation.invitation_token)

        # Assert
        assert result.id == invitation.id

    async def test_get_invitation_by_token_not_found(self, db_session):
        """Should raise ResourceNotFoundException if token not found"""
        # Arrange
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(ResourceNotFoundException):
            await service.get_invitation_by_token("invalid_token")


@pytest.mark.unit
class TestInvitationServiceGetWorkspaceInvitations:
    """Test get_workspace_invitations method"""

    async def test_get_workspace_invitations_all(self, db_session, setup_factories):
        """Should return all workspace invitations"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        inv1 = await setup_factories["invitation"].create(
            workspace_id=workspace.id,
            status="pending"
        )
        inv2 = await setup_factories["invitation"].create(
            workspace_id=workspace.id,
            status="accepted"
        )
        service = InvitationService(db_session)

        # Act
        result = await service.get_workspace_invitations(workspace.id)

        # Assert
        assert len(result) == 2

    async def test_get_workspace_invitations_filtered(self, db_session, setup_factories):
        """Should filter by status"""
        # Arrange
        workspace = await setup_factories["workspace"].create()
        await setup_factories["invitation"].create(
            workspace_id=workspace.id,
            status="pending"
        )
        await setup_factories["invitation"].create(
            workspace_id=workspace.id,
            status="accepted"
        )
        service = InvitationService(db_session)

        # Act
        result = await service.get_workspace_invitations(
            workspace.id,
            status="pending"
        )

        # Assert
        assert len(result) == 1
        assert result[0].status == "pending"


@pytest.mark.unit
class TestInvitationServiceAcceptInvitation:
    """Test accept_invitation method"""

    async def test_accept_invitation_success(self, db_session, setup_factories):
        """Should accept invitation and create membership"""
        # Arrange
        user = await setup_factories["user"].create(email="invitee@example.com")
        invitation = await setup_factories["invitation"].create(
            email="invitee@example.com",
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        service = InvitationService(db_session)

        # Act
        result = await service.accept_invitation(
            invitation_id=invitation.id,
            user_id=user.id
        )
        await db_session.refresh(invitation)

        # Assert
        assert invitation.status == "accepted"
        assert result["user_id"] == str(user.id)
        assert result["workspace_id"] == str(invitation.workspace_id)
        assert "membership_id" in result

    async def test_accept_invitation_not_pending(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if not pending"""
        # Arrange
        user = await setup_factories["user"].create()
        invitation = await setup_factories["invitation"].create(
            status="accepted"
        )
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.accept_invitation(
                invitation_id=invitation.id,
                user_id=user.id
            )

        assert "cannot accept" in exc_info.value.message

    async def test_accept_invitation_expired(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if expired"""
        # Arrange
        user = await setup_factories["user"].create()
        invitation = await setup_factories["invitation"].create(
            status="pending",
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.accept_invitation(
                invitation_id=invitation.id,
                user_id=user.id
            )

        assert "expired" in exc_info.value.message

    async def test_accept_invitation_email_mismatch(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if email doesn't match"""
        # Arrange
        user = await setup_factories["user"].create(email="wrong@example.com")
        invitation = await setup_factories["invitation"].create(
            email="correct@example.com",
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await service.accept_invitation(
                invitation_id=invitation.id,
                user_id=user.id
            )

        assert "does not match" in exc_info.value.message


@pytest.mark.unit
class TestInvitationServiceRevokeInvitation:
    """Test revoke_invitation method"""

    async def test_revoke_invitation_success(self, db_session, setup_factories):
        """Should successfully revoke pending invitation"""
        # Arrange
        invitation = await setup_factories["invitation"].create(status="pending")
        revoker = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act
        result = await service.revoke_invitation(
            invitation_id=invitation.id,
            revoked_by_user_id=revoker.id
        )

        # Assert
        assert result.status == "revoked"

    async def test_revoke_invitation_not_pending(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if not pending"""
        # Arrange
        invitation = await setup_factories["invitation"].create(status="accepted")
        revoker = await setup_factories["user"].create()
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException):
            await service.revoke_invitation(
                invitation_id=invitation.id,
                revoked_by_user_id=revoker.id
            )


@pytest.mark.unit
class TestInvitationServiceExpireOldInvitations:
    """Test expire_old_invitations method"""

    async def test_expire_old_invitations_success(self, db_session, setup_factories):
        """Should expire all old pending invitations"""
        # Arrange
        # Create expired invitation
        old_inv = await setup_factories["invitation"].create(
            status="pending",
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        # Create valid invitation
        valid_inv = await setup_factories["invitation"].create(
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        service = InvitationService(db_session)

        # Act
        count = await service.expire_old_invitations()
        await db_session.refresh(old_inv)
        await db_session.refresh(valid_inv)

        # Assert
        assert count == 1
        assert old_inv.status == "expired"
        assert valid_inv.status == "pending"

    async def test_expire_old_invitations_batch_limit(self, db_session, setup_factories):
        """Should respect batch size limit"""
        # Arrange
        for _ in range(5):
            await setup_factories["invitation"].create(
                status="pending",
                expires_at=datetime.utcnow() - timedelta(days=1)
            )
        service = InvitationService(db_session)

        # Act
        count = await service.expire_old_invitations(batch_size=3)

        # Assert
        assert count == 3


@pytest.mark.unit
class TestInvitationServiceResendInvitation:
    """Test resend_invitation method"""

    async def test_resend_invitation_success(self, db_session, setup_factories):
        """Should generate new token and extend expiry"""
        # Arrange
        invitation = await setup_factories["invitation"].create(
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=2)
        )
        original_token = invitation.invitation_token
        original_expiry = invitation.expires_at
        service = InvitationService(db_session)

        # Act
        result = await service.resend_invitation(
            invitation_id=invitation.id,
            extend_days=7
        )

        # Assert
        assert result.invitation_token != original_token
        assert result.expires_at > original_expiry

    async def test_resend_invitation_not_pending(self, db_session, setup_factories):
        """Should raise BusinessRuleViolationException if not pending"""
        # Arrange
        invitation = await setup_factories["invitation"].create(status="revoked")
        service = InvitationService(db_session)

        # Act & Assert
        with pytest.raises(BusinessRuleViolationException):
            await service.resend_invitation(invitation_id=invitation.id)
