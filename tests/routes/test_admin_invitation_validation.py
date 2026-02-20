import pytest

@pytest.mark.asyncio
async def test_validate_admin_invitation_token_invalid_returns_generic_message(async_client):
    response = await async_client.get("/api/v1/admin-invitations/not-a-real-token/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["status"] == "invalid"
    assert body["error_message"] == "Invitation is invalid or expired"