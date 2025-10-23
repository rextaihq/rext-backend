"""
Tests for AdminInvitationService

Tests cover:
- Creating admin invitations
- Validating super_admin permissions
- Accepting invitations
- Declining invitations
- Revoking invitations
- Resending invitations
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from src.services.admin_invitation_service import AdminInvitationService
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    DuplicateResourceException,
    BusinessRuleViolationException,
    UnauthorizedException,
    WrextValidationException
)


@pytest.fixture
async def super_admin_user(async_session):
    """Create a super admin user for testing."""
    # Create super_admin role if not exists
    super_admin_role = Role(
        id=uuid4(),
        name='super_admin',
        display_name='Super Admin',
        description='Platform super administrator'
    )
    async_session.add(super_admin_role)

    # Create user
    user = Users(
        id=uuid4(),
        email='superadmin@test.com',
        username='superadmin',
        password_hash='hashed_password',
        first_name='Super',
        last_name='Admin',
        display_name='Super Admin',
        status='active',
        email_verified=True
    )
    async_session.add(user)
    await async_session.flush()

    # Assign super_admin role
    user_role = UserRole(
        id=uuid4(),
        user_id=user.id,
        role_id=super_admin_role.id,
        workspace_id=None,  # Platform-level
        assigned_by_user_id=user.id,
        is_primary=True,
        assigned_at=datetime.utcnow()
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
async def regular_user(async_session):
    """Create a regular user for testing."""
    user = Users(
        id=uuid4(),
        email='regular@test.com',
        username='regular',
        password_hash='hashed_password',
        first_name='Regular',
        last_name='User',
        display_name='Regular User',
        status='active',
        email_verified=True
    )
    async_session.add(user)
    await async_session.commit()
    return user


@pytest.mark.asyncio
async def test_create_admin_invitation_success(async_session, super_admin_user):
    """Test successful creation of admin invitation."""
    service = AdminInvitationService(async_session)

    invitation = await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        message='Welcome to the team!',
        expiry_days=7
    )

    assert invitation.email == 'newadmin@test.com'
    assert invitation.admin_role == 'super_admin'
    assert invitation.status == 'pending'
    assert invitation.invitation_token is not None
    assert invitation.message == 'Welcome to the team!'
    assert invitation.invited_by_admin_id == super_admin_user.id
    assert not invitation.is_expired()
    assert invitation.can_be_accepted()


@pytest.mark.asyncio
async def test_create_admin_invitation_non_super_admin_fails(async_session, regular_user):
    """Test that non-super_admin cannot create admin invitations."""
    service = AdminInvitationService(async_session)

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.create_admin_invitation(
            email='newadmin@test.com',
            admin_role='super_admin',
            invited_by_admin_id=regular_user.id,
            expiry_days=7
        )

    assert "Only super admins" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_create_admin_invitation_invalid_role(async_session, super_admin_user):
    """Test that invalid admin role is rejected."""
    service = AdminInvitationService(async_session)

    with pytest.raises(WrextValidationException) as exc_info:
        await service.create_admin_invitation(
            email='newadmin@test.com',
            admin_role='invalid_role',
            invited_by_admin_id=super_admin_user.id,
            expiry_days=7
        )

    assert "not a valid admin role" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_create_admin_invitation_duplicate_email(async_session, super_admin_user):
    """Test that duplicate pending invitations are rejected."""
    service = AdminInvitationService(async_session)

    # Create first invitation
    await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )

    # Try to create duplicate
    with pytest.raises(DuplicateResourceException) as exc_info:
        await service.create_admin_invitation(
            email='newadmin@test.com',
            admin_role='super_admin',
            invited_by_admin_id=super_admin_user.id,
            expiry_days=7
        )

    assert "Pending admin invitation already exists" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_accept_admin_invitation_success(async_session, super_admin_user, regular_user):
    """Test successful acceptance of admin invitation."""
    service = AdminInvitationService(async_session)

    # Create invitation
    invitation = await service.create_admin_invitation(
        email=regular_user.email,
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Accept invitation
    accepted_invitation = await service.accept_admin_invitation(
        token=invitation.invitation_token,
        user_id=regular_user.id
    )

    assert accepted_invitation.status == 'accepted'
    assert accepted_invitation.accepted_at is not None
    assert accepted_invitation.accepted_by_user_id == regular_user.id
    assert not accepted_invitation.can_be_accepted()


@pytest.mark.asyncio
async def test_accept_admin_invitation_email_mismatch(async_session, super_admin_user, regular_user):
    """Test that email mismatch prevents acceptance."""
    service = AdminInvitationService(async_session)

    # Create invitation for different email
    invitation = await service.create_admin_invitation(
        email='different@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Try to accept with wrong user
    with pytest.raises(BusinessRuleViolationException) as exc_info:
        await service.accept_admin_invitation(
            token=invitation.invitation_token,
            user_id=regular_user.id
        )

    assert "This invitation is for" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_accept_admin_invitation_expired(async_session, super_admin_user, regular_user):
    """Test that expired invitations cannot be accepted."""
    service = AdminInvitationService(async_session)

    # Create invitation
    invitation = await service.create_admin_invitation(
        email=regular_user.email,
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )

    # Manually expire invitation
    invitation.expires_at = datetime.utcnow() - timedelta(days=1)
    await async_session.commit()

    # Try to accept
    with pytest.raises(BusinessRuleViolationException) as exc_info:
        await service.accept_admin_invitation(
            token=invitation.invitation_token,
            user_id=regular_user.id
        )

    assert "expired" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_decline_admin_invitation_success(async_session, super_admin_user):
    """Test successful decline of admin invitation."""
    service = AdminInvitationService(async_session)

    # Create invitation
    invitation = await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Decline invitation
    declined_invitation = await service.decline_admin_invitation(
        token=invitation.invitation_token,
        reason='Not interested at this time'
    )

    assert declined_invitation.status == 'declined'
    assert declined_invitation.declined_at is not None
    assert declined_invitation.declined_reason == 'Not interested at this time'
    assert not declined_invitation.can_be_accepted()


@pytest.mark.asyncio
async def test_revoke_admin_invitation_success(async_session, super_admin_user):
    """Test successful revocation of admin invitation."""
    service = AdminInvitationService(async_session)

    # Create invitation
    invitation = await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Revoke invitation
    revoked_invitation = await service.revoke_admin_invitation(
        invitation_id=invitation.id,
        revoked_by_admin_id=super_admin_user.id,
        reason='Position filled'
    )

    assert revoked_invitation.status == 'revoked'
    assert revoked_invitation.revoked_at is not None
    assert revoked_invitation.revoked_by_admin_id == super_admin_user.id
    assert revoked_invitation.revoked_reason == 'Position filled'
    assert not revoked_invitation.can_be_accepted()


@pytest.mark.asyncio
async def test_resend_admin_invitation_success(async_session, super_admin_user):
    """Test successful resending of admin invitation."""
    service = AdminInvitationService(async_session)

    # Create invitation
    invitation = await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    original_token = invitation.invitation_token
    original_expiry = invitation.expires_at

    # Resend invitation
    resent_invitation = await service.resend_admin_invitation(
        invitation_id=invitation.id,
        resent_by_admin_id=super_admin_user.id,
        expiry_days=14
    )

    assert resent_invitation.invitation_token != original_token
    assert resent_invitation.expires_at > original_expiry
    assert resent_invitation.status == 'pending'


@pytest.mark.asyncio
async def test_get_invitation_by_token(async_session, super_admin_user):
    """Test retrieving invitation by token."""
    service = AdminInvitationService(async_session)

    # Create invitation
    created_invitation = await service.create_admin_invitation(
        email='newadmin@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Retrieve by token
    retrieved_invitation = await service.get_invitation_by_token(
        created_invitation.invitation_token
    )

    assert retrieved_invitation.id == created_invitation.id
    assert retrieved_invitation.email == created_invitation.email


@pytest.mark.asyncio
async def test_get_all_invitations(async_session, super_admin_user):
    """Test listing all admin invitations."""
    service = AdminInvitationService(async_session)

    # Create multiple invitations
    await service.create_admin_invitation(
        email='admin1@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await service.create_admin_invitation(
        email='admin2@test.com',
        admin_role='support_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Get all invitations
    invitations = await service.get_all_invitations(limit=10)

    assert len(invitations) == 2
    assert all(inv.status == 'pending' for inv in invitations)


@pytest.mark.asyncio
async def test_get_all_invitations_with_status_filter(async_session, super_admin_user):
    """Test filtering invitations by status."""
    service = AdminInvitationService(async_session)

    # Create and decline one invitation
    invitation1 = await service.create_admin_invitation(
        email='admin1@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    await service.decline_admin_invitation(
        token=invitation1.invitation_token,
        reason='Test decline'
    )

    # Create another pending invitation
    await service.create_admin_invitation(
        email='admin2@test.com',
        admin_role='super_admin',
        invited_by_admin_id=super_admin_user.id,
        expiry_days=7
    )
    await async_session.commit()

    # Filter by status
    pending_invitations = await service.get_all_invitations(status='pending')
    declined_invitations = await service.get_all_invitations(status='declined')

    assert len(pending_invitations) == 1
    assert len(declined_invitations) == 1
    assert pending_invitations[0].status == 'pending'
    assert declined_invitations[0].status == 'declined'
