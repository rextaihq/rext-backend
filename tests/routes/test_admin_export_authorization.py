import pytest


@pytest.mark.asyncio
async def test_export_requires_super_admin(async_client, non_super_admin_token):
    response = await async_client.get(
        "/api/v1/admin/export/subscriptions",
        headers={"Authorization": f"Bearer {non_super_admin_token}"},
    )
    assert response.status_code == 403