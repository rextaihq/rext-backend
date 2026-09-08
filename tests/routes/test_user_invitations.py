"""
Tests for User Invitations Routes

These tests cover the user-facing invitation endpoints:
- GET /api/v1/user/invitations/pending
- POST /api/v1/user/invitations/{id}/decline
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select

from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.token_utils import create_access_token


def generate_auth_token(user_id, username: str, email: str) -> str:
    """Generate JWT token for testing"""
    token_data = {
        "identity": str(user_id),
        "username": username,
        "email": email,
        "roles": ["user"],
        "permissions": []
    }
    return create_access_token(token_data)


@pytest.mark.asyncio
async def test_get_pending_invitations_success(client, db_session):
    """
    Test retrieving pending invitations for a user.

    Scenario:
    - User has 2 pending invitations to different workspaces
    - Should return both invitations with workspace and role details
    """
    # Create inviter user
    inviter_id = uuid4()
    inviter = Users(
        id=inviter_id,
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        status="active",
        email_verified=True
    )
    db_session.add(inviter)

    # Create invitee user
    invitee_id = uuid4()
    invitee = Users(
        id=invitee_id,
        email="invitee@example.com",
        username="invitee",
        first_name="Invitee",
        last_name="User",
        status="active",
        email_verified=True
    )
    db_session.add(invitee)

    # Create two workspaces
    workspace1 = WorkspaceModel(
        id=uuid4(),
        slug="workspace-one",
        title="Workspace One",
        timezone="UTC",
        user_id=inviter_id
    )
    workspace2 = WorkspaceModel(
        id=uuid4(),
        slug="workspace-two",
        title="Workspace Two",
        timezone="UTC",
        user_id=inviter_id
    )
    db_session.add(workspace1)
    db_session.add(workspace2)

    # Get a role for invitations
    role_result = await db_session.execute(
        select(Role).where(Role.name == "user").limit(1)
    )
    role = role_result.scalar_one()

    # Create two pending invitations
    invitation1 = UserInvitations(
        id=uuid4(),
        email=invitee.email,
        workspace_id=workspace1.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=f"token_{uuid4().hex}",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_at=datetime.now(timezone.utc)
    )
    invitation2 = UserInvitations(
        id=uuid4(),
        email=invitee.email,
        workspace_id=workspace2.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=f"token_{uuid4().hex}",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(invitation1)
    db_session.add(invitation2)
    await db_session.commit()

    # Generate token for invitee
    token = generate_auth_token(invitee.id, invitee.username, invitee.email)

    # Make request
    response = await client.get(
        "/api/v1/user/invitations/pending",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True

    invitations_data = data["data"]["invitations"]
    assert len(invitations_data) == 2
    assert data["data"]["count"] == 2

    # Verify invitation structure
    inv = invitations_data[0]
    assert "workspace" in inv
    assert "role" in inv
    assert "invited_by" in inv
    assert "token" in inv
    assert "expires_at" in inv


@pytest.mark.asyncio
async def test_get_pending_invitations_empty(client, db_session):
    """Test retrieving pending invitations when user has none."""
    # Create user with no invitations
    user_id = uuid4()
    user = Users(
        id=user_id,
        email="no-invites@example.com",
        username="noinvites",
        first_name="No",
        last_name="Invites",
        status="active",
        email_verified=True
    )
    db_session.add(user)
    await db_session.commit()

    # Generate token
    token = generate_auth_token(user.id, user.username, user.email)

    # Make request
    response = await client.get(
        "/api/v1/user/invitations/pending",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["invitations"] == []
    assert data["data"]["count"] == 0


@pytest.mark.asyncio
async def test_decline_invitation_success(client, db_session):
    """Test successfully declining an invitation."""
    # Create inviter and invitee
    inviter_id = uuid4()
    inviter = Users(
        id=inviter_id,
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        status="active",
        email_verified=True
    )
    invitee_id = uuid4()
    invitee = Users(
        id=invitee_id,
        email="invitee@example.com",
        username="invitee",
        first_name="Invitee",
        last_name="User",
        status="active",
        email_verified=True
    )
    db_session.add(inviter)
    db_session.add(invitee)

    # Create workspace
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC",
        user_id=inviter_id
    )
    db_session.add(workspace)

    # Get role
    role_result = await db_session.execute(
        select(Role).where(Role.name == "user").limit(1)
    )
    role = role_result.scalar_one()

    # Create pending invitation
    invitation = UserInvitations(
        id=uuid4(),
        email=invitee.email,
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=f"token_{uuid4().hex}",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(invitation)
    await db_session.commit()

    # Generate token for invitee
    token = generate_auth_token(invitee.id, invitee.username, invitee.email)

    # Decline invitation
    response = await client.post(
        f"/api/v1/user/invitations/{invitation.id}/decline",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["invitation_id"] == str(invitation.id)
    assert data["data"]["status"] == "declined"

    # Verify invitation status updated in database
    await db_session.refresh(invitation)
    assert invitation.status == "declined"


@pytest.mark.asyncio
async def test_decline_invitation_wrong_user(client, db_session):
    """Test that user cannot decline invitation meant for different email."""
    # Create inviter
    inviter_id = uuid4()
    inviter = Users(
        id=inviter_id,
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        status="active",
        email_verified=True
    )
    db_session.add(inviter)

    # Create workspace
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC",
        user_id=inviter_id
    )
    db_session.add(workspace)

    # Get role
    role_result = await db_session.execute(
        select(Role).where(Role.name == "user").limit(1)
    )
    role = role_result.scalar_one()

    # Create invitation for user1@example.com
    invitation = UserInvitations(
        id=uuid4(),
        email="user1@example.com",
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=f"token_{uuid4().hex}",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        created_at=datetime.now(timezone.utc)
    )
    db_session.add(invitation)

    # Create different user (user2@example.com)
    user2_id = uuid4()
    user2 = Users(
        id=user2_id,
        email="user2@example.com",
        username="user2",
        first_name="User",
        last_name="Two",
        status="active",
        email_verified=True
    )
    db_session.add(user2)
    await db_session.commit()

    # Generate token for user2
    token = generate_auth_token(user2.id, user2.username, user2.email)

    # Try to decline invitation (should fail - wrong email)
    response = await client.post(
        f"/api/v1/user/invitations/{invitation.id}/decline",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assertions
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False

    # Verify invitation status unchanged
    await db_session.refresh(invitation)
    assert invitation.status == "pending"
