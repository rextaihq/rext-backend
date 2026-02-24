"""
Tests for AdminInvitationService invitation uniqueness and reinvitation flow.

Covers:
- Allowing reinvitation after an invitation is non-pending (revoked/declined/expired/accepted)
- Blocking multiple pending invitations for the same email (via service pre-check and DB constraint)
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.services.admin_invitation_service import AdminInvitationService
from src.api.middleware.exceptions import DuplicateResourceException, BusinessRuleViolationException


@pytest.fixture
async def admin_service(db_session):
    return AdminInvitationService(db_session)


@pytest.fixture
async def super_admin(db_session):
    """Create a super admin for testing."""
    # Ensure super_admin role exists
    result = await db_session.execute(select(Role).where(Role.name == "super_admin"))
    role = result.scalar_one_or_none()
    if not role:
        role = Role(name="super_admin", hierarchy_level=100)
        db_session.add(role)
        await db_session.flush()

    user = Users(
        email=f"admin_{uuid4().hex[:8]}@test.com",
        full_name="Super Admin",
        hashed_password="hashed",
        is_active=True,
        email_verified=True
    )
    db_session.add(user)
    await db_session.flush()
    
    from src.api.models.user_models.user_roles import UserRole
    user_role = UserRole(user_id=user.id, role_id=role.id, is_primary=True)
    db_session.add(user_role)
    await db_session.flush()
    
    return user


@pytest.mark.asyncio
async def test_reinvitation_after_non_pending_status(db_session, admin_service, super_admin):
    """Verify that an email can be invited again if the previous invite is not pending."""
    email = "test_reinvite@example.com"
    
    # 1. Create first invitation
    invite1 = await admin_service.create_admin_invitation(
        email=email,
        admin_role="super_admin",
        invited_by_admin_id=super_admin.id
    )
    assert invite1.status == "pending"
    
    # 2. Mark it as revoked
    await admin_service.revoke_admin_invitation(
        invitation_id=invite1.id,
        revoked_by_admin_id=super_admin.id,
        reason="Testing reinvite"
    )
    await db_session.flush()
    
    # 3. Attempt to create a new invitation for the same email
    invite2 = await admin_service.create_admin_invitation(
        email=email,
        admin_role="super_admin",
        invited_by_admin_id=super_admin.id
    )
    assert invite2.status == "pending"
    assert invite2.id != invite1.id


@pytest.mark.asyncio
async def test_duplicate_pending_invitation_blocked(db_session, admin_service, super_admin):
    """Verify that creating a second pending invitation for the same email is blocked."""
    email = "test_duplicate@example.com"
    
    # 1. Create first invitation
    await admin_service.create_admin_invitation(
        email=email,
        admin_role="super_admin",
        invited_by_admin_id=super_admin.id
    )
    
    # 2. Attempt to create another pending invitation
    with pytest.raises(DuplicateResourceException) as exc:
        await admin_service.create_admin_invitation(
            email=email,
            admin_role="super_admin",
            invited_by_admin_id=super_admin.id
        )
    assert "Pending admin invitation already exists" in str(exc.value)


@pytest.mark.asyncio
async def test_race_condition_uniqueness_handling(db_session, admin_service, super_admin):
    """Verify that the DB-level uniqueness constraint catches race conditions."""
    email = "test_race@example.com"
    
    # Simulate first invitation already in DB but not committed yet (passed the service check)
    invite1 = PlatformAdminInvitations(
        email=email,
        admin_role="super_admin",
        invited_by_admin_id=super_admin.id,
        invitation_token="token1",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db_session.add(invite1)
    await db_session.flush()
    
    # Manually attempt to add another one with same email/pending status
    # bypassing the service's select check to simulate a race condition
    invite2 = PlatformAdminInvitations(
        email=email,
        admin_role="super_admin",
        invited_by_admin_id=super_admin.id,
        invitation_token="token2",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db_session.add(invite2)
    
    with pytest.raises(IntegrityError) as exc:
        await db_session.flush()
    
    assert "uq_admin_invitation_email_pending" in str(exc.value)
