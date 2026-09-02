"""
Security tests for Invitation Routes.

Tests the fix for Task-331: Re-Enable Email Verification on Token-Based Invitation Acceptance.
"""

import pytest

from src.api.models.user_models.invitations import UserInvitations
from src.api.security.token_utils import create_access_token


def generate_auth_token(user_id, username_dummy: str, email: str) -> str:
    """Generate JWT token for testing"""
    token_data = {
        "identity": str(user_id),
        "username": username_dummy,
        "email": email,
        "roles": ["user"],
        "permissions": [],
    }
    return create_access_token(token_data)


@pytest.mark.asyncio
async def test_accept_invitation_email_mismatch_rejected(client, db_session, setup_factories):
    """
    Verify that a user cannot accept an invitation meant for a different email.
    """
    UserFactory = setup_factories["user"]
    InvitationFactory = setup_factories["invitation"]

    # 1. Create target user (the one who should accept)
    await UserFactory.create(email="target@example.com", display_name="Target User")

    # 2. Create attacker user (the one who shouldn't be able to accept)
    attacker_user = await UserFactory.create(
        email="attacker@example.com", display_name="Attacker User"
    )

    # 3. Create invitation for target user
    invitation = await InvitationFactory.create(email="target@example.com")

    # 4. Try to accept as attacker
    attacker_token = generate_auth_token(attacker_user.id, "attacker_user", attacker_user.email)
    response = await client.post(
        f"/api/v1/invitations/{invitation.invitation_token}/accept",
        headers={"Authorization": f"Bearer {attacker_token}"},
    )

    # 5. Assertions
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["rule_name"] == "email_must_match_invitation"
    assert "Please sign in with the correct account" in data["error"]["message"]

    # 6. Verify invitation is still pending
    await db_session.refresh(invitation)
    assert invitation.status == "pending"


@pytest.mark.asyncio
async def test_accept_invitation_matching_email_success(client, db_session, setup_factories):
    """
    Verify that a user can accept an invitation meant for their email.
    """
    UserFactory = setup_factories["user"]
    InvitationFactory = setup_factories["invitation"]

    # 1. Create target user
    target_user = await UserFactory.create(email="target@example.com", display_name="Target User")

    # 2. Create invitation for target user
    invitation = await InvitationFactory.create(email="target@example.com")

    # 3. Accept as target
    target_token = generate_auth_token(target_user.id, "target_user", target_user.email)
    response = await client.post(
        f"/api/v1/invitations/{invitation.invitation_token}/accept",
        headers={"Authorization": f"Bearer {target_token}"},
    )

    # 4. Assertions
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["message"] == f"Welcome to {data['data']['workspace_name']}!"

    # 5. Verify invitation is accepted
    await db_session.refresh(invitation)
    assert invitation.status == "accepted"


@pytest.mark.asyncio
async def test_accept_invitation_case_insensitive_success(client, db_session, setup_factories):
    """
    Verify that email comparison is case-insensitive.
    """
    UserFactory = setup_factories["user"]
    InvitationFactory = setup_factories["invitation"]

    # 1. Create target user with lowercase email
    target_user = await UserFactory.create(email="target@example.com", display_name="Target User")

    # 2. Create invitation for target user with mixed-case email
    invitation = await InvitationFactory.create(email="Target@Example.Com")

    # 3. Accept as target
    target_token = generate_auth_token(target_user.id, "target_user", target_user.email)
    response = await client.post(
        f"/api/v1/invitations/{invitation.invitation_token}/accept",
        headers={"Authorization": f"Bearer {target_token}"},
    )

    # 4. Assertions
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True

    # 5. Verify invitation is accepted
    await db_session.refresh(invitation)
    assert invitation.status == "accepted"
