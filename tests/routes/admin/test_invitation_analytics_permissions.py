import pytest
from httpx import AsyncClient
from uuid import UUID

@pytest.mark.asyncio
async def test_invitation_analytics_allows_global_admin_scope(client: AsyncClient, admin_auth_headers: dict):
    """
    Test that the invitation analytics endpoint allows global admin access (without workspace_id).
    """
    response = await client.get("/api/v1/admin/invitations/analytics", headers=admin_auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

@pytest.mark.asyncio
async def test_invitation_analytics_rejects_unauthorized_workspace(client: AsyncClient, admin_auth_headers: dict):
    """
    Test that the invitation analytics endpoint rejects unauthorized workspace access.
    A random UUID is used to simulate an unauthorized workspace.
    """
    random_workspace_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(
        f"/api/v1/admin/invitations/analytics?workspace_id={random_workspace_id}",
        headers=admin_auth_headers,
    )
    # The new internal check should raise RextAuthorizationException -> 403
    assert response.status_code == 403
