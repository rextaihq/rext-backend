"""
Tests for /register-with-invitation endpoint

This test suite covers:
- Successful registration with valid invitation
- Expired invitation handling
- Email mismatch validation
- Duplicate user prevention
- Invalid invitation token handling
- Workspace membership creation
- Email verification skip for invited users
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timedelta
from sqlalchemy import select

from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.user_models.roles import Role


@pytest.mark.asyncio
async def test_register_with_valid_invitation(async_client, async_db):
    """
    Test successful registration with valid invitation token.

    Expected behavior:
    - User account created
    - Email marked as verified (skip verification step)
    - Invitation accepted
    - Workspace membership created
    - Returns user + workspace data
    """
    # Arrange: Create workspace
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    # Create inviter user
    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    # Create role
    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    # Create invitation
    invitation_token = "test_invitation_token_123"
    invitation_email = "newuser@example.com"
    invitation = UserInvitations(
        id=uuid4(),
        email=invitation_email,
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Register with invitation
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": invitation_email,
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Response
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert "user" in data["data"]
    assert "workspace" in data["data"]
    assert data["data"]["invitation_accepted"] is True
    assert data["data"]["user"]["email"] == invitation_email
    assert data["data"]["user"]["email_verified"] is True  # Auto-verified
    assert data["data"]["workspace"]["slug"] == "test-workspace"

    # Assert: User created in database
    result = await async_db.execute(
        select(Users).where(Users.email == invitation_email)
    )
    created_user = result.scalar_one_or_none()
    assert created_user is not None
    assert created_user.email_verified is True
    assert created_user.email_verified_at is not None

    # Assert: Invitation accepted
    await async_db.refresh(invitation)
    assert invitation.status == "accepted"

    # Assert: Workspace membership created
    result = await async_db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.user_id == created_user.id,
            WorkspaceMembers.workspace_id == workspace.id
        )
    )
    membership = result.scalar_one_or_none()
    assert membership is not None
    assert membership.status == "active"
    assert membership.invitation_id == invitation.id


@pytest.mark.asyncio
async def test_register_with_expired_invitation(async_client, async_db):
    """
    Test registration fails with expired invitation.

    Expected behavior:
    - Returns 400 error
    - Invitation status updated to 'expired'
    - User account NOT created
    """
    # Arrange: Create workspace and invitation (expired)
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    # Create EXPIRED invitation
    invitation_token = "expired_token_123"
    invitation = UserInvitations(
        id=uuid4(),
        email="newuser@example.com",
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="pending",
        expires_at=datetime.utcnow() - timedelta(days=1)  # Expired yesterday
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Try to register with expired invitation
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Request fails
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "expired" in data["message"].lower()

    # Assert: Invitation marked as expired
    await async_db.refresh(invitation)
    assert invitation.status == "expired"

    # Assert: User NOT created
    result = await async_db.execute(
        select(Users).where(Users.email == "newuser@example.com")
    )
    user = result.scalar_one_or_none()
    assert user is None


@pytest.mark.asyncio
async def test_register_with_email_mismatch(async_client, async_db):
    """
    Test registration fails when email doesn't match invitation.

    Expected behavior:
    - Returns 400 error
    - User account NOT created
    - Invitation remains pending

    Security: This prevents invitation token hijacking
    """
    # Arrange: Create workspace and invitation
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    invitation_token = "test_token_123"
    invitation = UserInvitations(
        id=uuid4(),
        email="invited@example.com",  # Invitation for this email
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Try to register with DIFFERENT email
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": "different@example.com",  # Wrong email!
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Request fails with clear error
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "email must match" in data["message"].lower()

    # Assert: User NOT created
    result = await async_db.execute(
        select(Users).where(Users.email == "different@example.com")
    )
    user = result.scalar_one_or_none()
    assert user is None

    # Assert: Invitation still pending (not consumed)
    await async_db.refresh(invitation)
    assert invitation.status == "pending"


@pytest.mark.asyncio
async def test_register_with_duplicate_email(async_client, async_db):
    """
    Test registration fails when user already exists.

    Expected behavior:
    - Returns 400 error (duplicate user)
    - Existing user unchanged
    - Invitation remains pending
    """
    # Arrange: Create existing user
    existing_user = Users(
        id=uuid4(),
        email="existing@example.com",
        username="existing",
        first_name="Existing",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(existing_user)

    # Create workspace and invitation
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    invitation_token = "test_token_123"
    invitation = UserInvitations(
        id=uuid4(),
        email="existing@example.com",
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Try to register with existing email
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": "existing@example.com",
            "username": "newusername",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Request fails
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "duplicate" in data["message"].lower() or "already exists" in data["message"].lower()


@pytest.mark.asyncio
async def test_register_with_invalid_token(async_client, async_db):
    """
    Test registration fails with invalid/non-existent token.

    Expected behavior:
    - Returns 404 error
    - User account NOT created
    """
    # Act: Try to register with non-existent token
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": "invalid_token_does_not_exist"
        }
    )

    # Assert: Request fails
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False

    # Assert: User NOT created
    result = await async_db.execute(
        select(Users).where(Users.email == "newuser@example.com")
    )
    user = result.scalar_one_or_none()
    assert user is None


@pytest.mark.asyncio
async def test_register_with_already_accepted_invitation(async_client, async_db):
    """
    Test registration fails when invitation already accepted.

    Expected behavior:
    - Returns 400 error
    - User account NOT created
    """
    # Arrange: Create workspace with already-accepted invitation
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    invitation_token = "already_used_token"
    invitation = UserInvitations(
        id=uuid4(),
        email="newuser@example.com",
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="accepted",  # Already accepted!
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Try to use already-accepted invitation
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Request fails
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert "accepted" in data["message"].lower()


@pytest.mark.asyncio
async def test_register_with_invitation_creates_active_membership(async_client, async_db):
    """
    Test that workspace membership is created with 'active' status.

    Expected behavior:
    - Membership created
    - Status is 'active'
    - joined_at timestamp set
    - invitation_id references the invitation
    """
    # Arrange: Create complete setup
    workspace = WorkspaceModel(
        id=uuid4(),
        slug="test-workspace",
        title="Test Workspace",
        timezone="UTC"
    )
    async_db.add(workspace)

    inviter = Users(
        id=uuid4(),
        email="inviter@example.com",
        username="inviter",
        first_name="Inviter",
        last_name="User",
        password="hashed_password",
        status="active",
        email_verified=True
    )
    async_db.add(inviter)

    role = Role(
        id=uuid4(),
        name="editor",
        display_name="Editor",
        workspace_id=workspace.id
    )
    async_db.add(role)
    await async_db.flush()

    invitation_token = "test_token_123"
    invitation_email = "newuser@example.com"
    invitation = UserInvitations(
        id=uuid4(),
        email=invitation_email,
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=invitation_token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    async_db.add(invitation)
    await async_db.commit()

    # Act: Register with invitation
    response = await async_client.post(
        "/api/v1/user/register-with-invitation",
        json={
            "email": invitation_email,
            "username": "newuser",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "invitation_token": invitation_token
        }
    )

    # Assert: Success
    assert response.status_code == 201

    # Assert: Membership details
    result = await async_db.execute(
        select(Users).where(Users.email == invitation_email)
    )
    created_user = result.scalar_one()

    result = await async_db.execute(
        select(WorkspaceMembers).where(
            WorkspaceMembers.user_id == created_user.id
        )
    )
    membership = result.scalar_one()

    assert membership.status == "active"
    assert membership.workspace_id == workspace.id
    assert membership.invitation_id == invitation.id
    assert membership.joined_at is not None
    assert membership.last_activity_at is not None
